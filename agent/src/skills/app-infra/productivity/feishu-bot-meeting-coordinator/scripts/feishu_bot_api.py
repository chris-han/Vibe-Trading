"""Feishu Bot Meeting Coordinator Helper Script.

ARCHITECTURE CONTRACT (Semantier Deterministic File Ops + Per-Task Sandboxing)
================================================================================

This script is a **materialized helper** for the feishu-bot-meeting-coordinator skill.

How it works:
1. When the skill is invoked, the /agent wrapper layer detects it needs this script.
2. The wrapper **materializes** this file from:
   agent/src/skills/app-infra/productivity/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py
3. The wrapper copies it to the task sandbox at:
   .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py
4. The task execution references ONLY the sandboxed path (relative).
5. When the task completes, the wrapper cleans up the materialized copy.

KEY INVARIANTS:
- This script is discovered/copied by the wrapper layer, NOT by prompts or manual invocation.
- Do NOT hardcode absolute system paths in this file.
- Do NOT assume a fixed location on disk; the script may be materialized anywhere in the sandbox.
- DO use relative paths or environment discovery (e.g., finding agent/.env via traversal).

USAGE:
    # Always invoked from the task sandbox as:
    python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py <command> [args]

    # Example:
    python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \\
      search-chats --query "管理层群"

CREDENTIAL LOADING:
    This script discovers and loads credentials from agent/.env by traversing up
    the directory tree (working regardless of where the sandbox lives). Do NOT
    store hardcoded API keys or paths in this file.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_ORGANIZER_IDENTITY = "semantier"
DEFAULT_CONTACT_SCOPE = "contacts-added-to-bot"
DEFAULT_NEGOTIATION_ROUNDS = 3


def _load_env_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ[key] = value


def _bootstrap_env() -> None:
    # Load agent/.env from the agent home directory discovered at runtime.
    # Finds the agent folder by traversing up from this script's location,
    # working regardless of where the agent installation resides.
    script_path = Path(__file__).resolve()
    
    # Discover agent home by traversing up from this script's location
    agent_env_path: Path | None = None
    for parent in [script_path, *script_path.parents]:
        if parent.name == "agent" and parent.is_dir():
            agent_env_path = parent / ".env"
            break
    
    # Load credentials from the agent home .env file
    if agent_env_path and agent_env_path.is_file():
        _load_env_file(agent_env_path)


_bootstrap_env()


class FeishuSkillError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = payload or {}


@dataclass
class AttendeeNegotiationState:
    attendee_open_id: str
    display_name: str
    accepted_slots: set[str] = field(default_factory=set)
    declined_slots: set[str] = field(default_factory=set)
    rounds_responded: set[int] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attendee_open_id": self.attendee_open_id,
            "display_name": self.display_name,
            "accepted_slots": sorted(self.accepted_slots),
            "declined_slots": sorted(self.declined_slots),
            "rounds_responded": sorted(self.rounds_responded),
            "notes": list(self.notes),
        }


@dataclass
class MeetingNegotiationState:
    negotiation_id: str
    title: str
    initiator_open_id: str
    timezone: str
    duration_minutes: int
    max_rounds: int
    current_round: int
    candidate_slots: list[str]
    attendees: dict[str, AttendeeNegotiationState]
    status: str = "negotiating"
    agreed_slot: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "negotiation_id": self.negotiation_id,
            "title": self.title,
            "initiator_open_id": self.initiator_open_id,
            "timezone": self.timezone,
            "duration_minutes": self.duration_minutes,
            "max_rounds": self.max_rounds,
            "current_round": self.current_round,
            "candidate_slots": list(self.candidate_slots),
            "status": self.status,
            "agreed_slot": self.agreed_slot,
            "attendees": {key: value.to_dict() for key, value in self.attendees.items()},
        }


def _to_slot_key(value: str, timezone_name: str) -> str:
    dt = _parse_time(value, timezone_name)
    return dt.isoformat()


def _deserialize_negotiation_state(state_payload: dict[str, Any]) -> MeetingNegotiationState:
    attendees_payload = state_payload.get("attendees") or {}
    attendees: dict[str, AttendeeNegotiationState] = {}
    for key, value in attendees_payload.items():
        if not isinstance(value, dict):
            continue
        attendee_open_id = str(value.get("attendee_open_id") or key).strip()
        if not attendee_open_id:
            continue
        attendees[attendee_open_id] = AttendeeNegotiationState(
            attendee_open_id=attendee_open_id,
            display_name=str(value.get("display_name") or attendee_open_id),
            accepted_slots=set(str(item) for item in value.get("accepted_slots") or []),
            declined_slots=set(str(item) for item in value.get("declined_slots") or []),
            rounds_responded=set(int(item) for item in value.get("rounds_responded") or []),
            notes=[str(item) for item in value.get("notes") or []],
        )

    return MeetingNegotiationState(
        negotiation_id=str(state_payload.get("negotiation_id") or uuid.uuid4().hex),
        title=str(state_payload.get("title") or ""),
        initiator_open_id=str(state_payload.get("initiator_open_id") or "").strip(),
        timezone=str(state_payload.get("timezone") or DEFAULT_TIMEZONE),
        duration_minutes=int(state_payload.get("duration_minutes") or 30),
        max_rounds=max(int(state_payload.get("max_rounds") or DEFAULT_NEGOTIATION_ROUNDS), 1),
        current_round=max(int(state_payload.get("current_round") or 1), 1),
        candidate_slots=[str(item) for item in state_payload.get("candidate_slots") or []],
        attendees=attendees,
        status=str(state_payload.get("status") or "negotiating"),
        agreed_slot=str(state_payload.get("agreed_slot") or "").strip() or None,
    )


def _env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        # Provide helpful error message with debugging info
        loaded_from_env = "FEISHU_APP_ID" in os.environ or "FEISHU_APP_SECRET" in os.environ
        error_msg = f"Missing required environment variable: {name}"
        if not loaded_from_env:
            error_msg += " (no Feishu credentials loaded from .env)"
        raise FeishuSkillError(error_msg)
    return value


def _base_url() -> str:
    domain = (os.getenv("FEISHU_DOMAIN") or "feishu").strip().lower()
    return "https://open.larksuite.com" if domain == "lark" else "https://open.feishu.cn"


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    session: requests.Session | None = None,
    return_data: bool = True,
) -> dict[str, Any]:
    client = session or requests.Session()
    response = client.request(method, url, headers=headers, json=body, params=params, timeout=20)
    response.raise_for_status()
    payload = response.json() if response.text else {}
    if not isinstance(payload, dict):
        raise FeishuSkillError(f"Feishu API returned a non-object payload for {url}")
    if int(payload.get("code") or 0) != 0:
        raise FeishuSkillError(
            payload.get("msg") or f"Feishu API error for {url}",
            payload=payload,
        )
    if not return_data:
        return payload
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _tenant_access_token(session: requests.Session | None = None) -> str:
    app_id = _env("FEISHU_APP_ID")
    app_secret = _env("FEISHU_APP_SECRET")
    data = _http_json(
        "POST",
        f"{_base_url()}/open-apis/auth/v3/tenant_access_token/internal",
        headers={"Content-Type": "application/json; charset=utf-8"},
        body={"app_id": app_id, "app_secret": app_secret},
        session=session,
        return_data=False,
    )
    token = str(data.get("tenant_access_token") or "").strip()
    if not token:
        raise FeishuSkillError("Feishu tenant token response did not include tenant_access_token", payload=data)
    return token


def _openapi_request(method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None, session: requests.Session | None = None) -> dict[str, Any]:
    token = _tenant_access_token(session=session)
    return _http_json(
        method,
        f"{_base_url()}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        body=body,
        params=params,
        session=session,
    )


def _openapi_request_with_token(
    method: str,
    path: str,
    *,
    access_token: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    token = access_token.strip()
    if not token:
        raise FeishuSkillError("Missing user access token for user-scoped Feishu API")
    return _http_json(
        method,
        f"{_base_url()}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        body=body,
        params=params,
        session=session,
    )


def _normalize_department_names(user: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in user.get("department_path") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def _score_candidate(query: str, user: dict[str, Any]) -> tuple[float, str]:
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return 0.0, "empty_query"

    fields = [
        ("display_name", str(user.get("name") or "").strip()),
        ("english_name", str(user.get("en_name") or "").strip()),
        ("email", str(user.get("email") or user.get("enterprise_email") or "").strip()),
        ("open_id", str(user.get("open_id") or "").strip()),
    ]
    for field_name, value in fields:
        if value and value.casefold() == normalized_query:
            return 1.0, f"exact_{field_name}"
    for field_name, value in fields:
        if value and normalized_query in value.casefold():
            return 0.7, f"partial_{field_name}"
    return 0.0, "no_match"


def _normalize_contact_candidate(query: str, user: dict[str, Any]) -> dict[str, Any] | None:
    score, match_reason = _score_candidate(query, user)
    open_id = str(user.get("open_id") or "").strip()
    if score <= 0.0 or not open_id:
        return None
    avatar = user.get("avatar") if isinstance(user.get("avatar"), dict) else {}
    avatar_url = str(avatar.get("avatar_72") or avatar.get("avatar_240") or "").strip() or None
    return {
        "display_name": str(user.get("name") or user.get("en_name") or open_id),
        "open_id": open_id,
        "union_id": str(user.get("union_id") or "").strip() or None,
        "avatar_url": avatar_url,
        "email": str(user.get("email") or user.get("enterprise_email") or "").strip() or None,
        "department_names": _normalize_department_names(user),
        "match_reason": match_reason,
        "score": score,
    }


def search_contacts(query: str, *, limit: int = 10, session: requests.Session | None = None) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        raise FeishuSkillError("query is required")

    seen: dict[str, dict[str, Any]] = {}
    page_token: str | None = None
    for _ in range(5):
        params: dict[str, Any] = {
            "department_id": "0",
            "department_id_type": "department_id",
            "user_id_type": "open_id",
            "page_size": 50,
        }
        if page_token:
            params["page_token"] = page_token
        data = _openapi_request(
            "GET",
            "/open-apis/contact/v3/users/find_by_department",
            params=params,
            session=session,
        )
        items = data.get("items") or data.get("user_list") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate = _normalize_contact_candidate(normalized_query, item)
            if candidate is None:
                continue
            seen[candidate["open_id"]] = candidate
            if len(seen) >= limit:
                break
        if len(seen) >= limit:
            break
        if not data.get("has_more"):
            break
        page_token = str(data.get("page_token") or "").strip() or None
        if not page_token:
            break

    candidates = sorted(seen.values(), key=lambda item: (-float(item["score"]), item["display_name"]))[:limit]
    return {
        "query": normalized_query,
        "organizer_identity": DEFAULT_ORGANIZER_IDENTITY,
        "contact_scope": DEFAULT_CONTACT_SCOPE,
        "candidates": candidates,
    }


def _score_chat_candidate(query: str, chat: dict[str, Any]) -> tuple[float, str]:
    normalized_query = query.strip().casefold()
    name = str(chat.get("name") or "").strip()
    if not normalized_query or not name:
        return 0.0, "empty_query_or_name"
    normalized_name = name.casefold()
    if normalized_name == normalized_query:
        return 1.0, "exact_chat_name"
    if normalized_query in normalized_name:
        return 0.8, "partial_chat_name"
    if "群" in normalized_query:
        simplified = normalized_query.replace("群里的所有人", "").replace("群里所有人", "").replace("群", "").strip()
        if simplified and simplified in normalized_name:
            return 0.7, "normalized_group_phrase"
    return 0.0, "no_match"


def search_chats(query: str, *, limit: int = 10, session: requests.Session | None = None) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        raise FeishuSkillError("query is required")

    matches: list[dict[str, Any]] = []
    page_token: str | None = None
    for _ in range(5):
        params: dict[str, Any] = {"page_size": 50}
        if page_token:
            params["page_token"] = page_token
        data = _openapi_request("GET", "/open-apis/im/v1/chats", params=params, session=session)
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            score, reason = _score_chat_candidate(normalized_query, item)
            if score <= 0.0:
                continue
            chat_id = str(item.get("chat_id") or "").strip()
            if not chat_id:
                continue
            matches.append(
                {
                    "chat_id": chat_id,
                    "name": str(item.get("name") or chat_id),
                    "description": str(item.get("description") or "").strip() or None,
                    "score": score,
                    "match_reason": reason,
                }
            )
        if not data.get("has_more"):
            break
        page_token = str(data.get("page_token") or "").strip() or None
        if not page_token:
            break

    matches.sort(key=lambda item: (-float(item["score"]), str(item["name"])))
    return {"query": normalized_query, "candidates": matches[:limit]}


def get_chat_members(chat_id: str, *, session: requests.Session | None = None) -> list[dict[str, Any]]:
    normalized_chat_id = chat_id.strip()
    if not normalized_chat_id:
        raise FeishuSkillError("chat_id is required")

    members: list[dict[str, Any]] = []
    page_token: str | None = None
    for _ in range(5):
        params: dict[str, Any] = {"member_id_type": "open_id", "page_size": 50}
        if page_token:
            params["page_token"] = page_token
        data = _openapi_request(
            "GET",
            f"/open-apis/im/v1/chats/{normalized_chat_id}/members",
            params=params,
            session=session,
        )
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            open_id = str(item.get("member_id") or item.get("open_id") or "").strip()
            if not open_id:
                continue
            members.append(
                {
                    "open_id": open_id,
                    "display_name": str(item.get("name") or open_id),
                }
            )
        if not data.get("has_more"):
            break
        page_token = str(data.get("page_token") or "").strip() or None
        if not page_token:
            break
    return members


def _resolve_group_phrase_attendees(group_phrase: str, *, session: requests.Session | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    chats = search_chats(group_phrase, limit=5, session=session).get("candidates") or []
    if not chats:
        raise FeishuSkillError("No matching group/chat found", payload={"group_phrase": group_phrase})
    top_chat = chats[0]
    if len(chats) > 1 and float(chats[0].get("score") or 0.0) == float(chats[1].get("score") or 0.0):
        raise FeishuSkillError(
            "Ambiguous group/chat match",
            payload={"group_phrase": group_phrase, "candidates": chats[:3]},
        )

    members = get_chat_members(str(top_chat.get("chat_id") or ""), session=session)
    if not members:
        raise FeishuSkillError("Matched group/chat has no resolvable members", payload={"chat": top_chat})

    attendee_results = [
        {
            "requested": group_phrase,
            "status": "resolved",
            "display_name": item["display_name"],
            "open_id": item["open_id"],
            "match_reason": "group_member",
            "source_chat_id": top_chat.get("chat_id"),
            "source_chat_name": top_chat.get("name"),
        }
        for item in members
    ]
    resolved_attendees = [{"type": "user", "user_id": item["open_id"], "is_optional": False} for item in members]
    return attendee_results, resolved_attendees


def _resolve_email_attendee(email: str, *, session: requests.Session | None = None) -> dict[str, Any] | None:
    data = _openapi_request(
        "POST",
        "/open-apis/contact/v3/users/batch_get_id",
        params={"user_id_type": "open_id"},
        body={"emails": [email], "include_resigned": False},
        session=session,
    )
    user_list = data.get("user_list") or []
    if not user_list or not isinstance(user_list[0], dict):
        return None
    user = user_list[0]
    open_id = str(user.get("open_id") or "").strip()
    if not open_id:
        return None
    return {
        "display_name": str(user.get("name") or user.get("email") or open_id),
        "open_id": open_id,
        "union_id": str(user.get("union_id") or "").strip() or None,
        "email": str(user.get("email") or email).strip() or None,
        "department_names": [],
        "match_reason": "exact_email",
        "score": 1.0,
    }


def _normalize_attendee_spec(raw_item: Any) -> dict[str, str | None]:
    if isinstance(raw_item, str):
        value = raw_item.strip()
        return {"name": None if "@" in value else value or None, "open_id": None, "email": value if "@" in value else None}
    if not isinstance(raw_item, dict):
        raise FeishuSkillError(f"Unsupported attendee spec: {raw_item!r}")
    normalized = {
        "name": str(raw_item.get("name") or raw_item.get("display_name") or "").strip() or None,
        "open_id": str(raw_item.get("open_id") or "").strip() or None,
        "email": str(raw_item.get("email") or "").strip() or None,
    }
    if not any(normalized.values()):
        raise FeishuSkillError(f"Unsupported attendee spec: {raw_item!r}")
    return normalized


def _parse_time(value: str, timezone_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise FeishuSkillError(f"Unsupported time format: {value}") from exc
    timezone = ZoneInfo(timezone_name)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _build_time_info(dt: datetime, timezone_name: str) -> dict[str, str]:
    return {"timestamp": str(int(dt.timestamp())), "timezone": timezone_name}


def _primary_calendar_id(*, session: requests.Session | None = None) -> str:
    data = _openapi_request("POST", "/open-apis/calendar/v4/calendars/primary", session=session)
    if isinstance(data.get("calendar"), dict):
        calendar_id = str(data["calendar"].get("calendar_id") or "").strip()
        if calendar_id:
            return calendar_id
    calendars = data.get("calendars") or []
    for item in calendars:
        if not isinstance(item, dict):
            continue
        calendar_id = str(item.get("calendar_id") or "").strip()
        if calendar_id:
            return calendar_id
    raise FeishuSkillError("Feishu primary calendar lookup returned no calendar_id", payload=data)


def _primary_calendar_id_for_user(user_open_id: str, *, session: requests.Session | None = None) -> str:
    target = user_open_id.strip()
    if not target:
        raise FeishuSkillError("user_open_id is required for primary calendar lookup")
    data = _openapi_request(
        "POST",
        "/open-apis/calendar/v4/calendars/primary",
        params={"user_id": target, "user_id_type": "open_id"},
        session=session,
    )
    if isinstance(data.get("calendar"), dict):
        calendar_id = str(data["calendar"].get("calendar_id") or "").strip()
        if calendar_id:
            return calendar_id
    calendars = data.get("calendars") or []
    for item in calendars:
        if not isinstance(item, dict):
            continue
        calendar_id = str(item.get("calendar_id") or "").strip()
        if calendar_id:
            return calendar_id
    raise FeishuSkillError(
        "Feishu user primary calendar lookup returned no calendar_id",
        payload={"user_open_id": target, "data": data},
    )


def start_negotiation(
    *,
    title: str,
    initiator_open_id: str,
    attendee_open_ids: list[str],
    candidate_slots: list[str],
    duration_minutes: int,
    timezone: str = DEFAULT_TIMEZONE,
    max_rounds: int = DEFAULT_NEGOTIATION_ROUNDS,
) -> dict[str, Any]:
    if not title.strip():
        raise FeishuSkillError("title is required")
    if not initiator_open_id.strip():
        raise FeishuSkillError("initiator_open_id is required")
    if duration_minutes <= 0:
        raise FeishuSkillError("duration_minutes must be greater than zero")

    slots = []
    seen_slots: set[str] = set()
    for raw_slot in candidate_slots:
        slot = _to_slot_key(raw_slot, timezone)
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        slots.append(slot)
    if not slots:
        raise FeishuSkillError("At least one candidate slot is required")

    attendees: dict[str, AttendeeNegotiationState] = {}
    for attendee_open_id in attendee_open_ids:
        attendee = attendee_open_id.strip()
        if not attendee:
            continue
        attendees[attendee] = AttendeeNegotiationState(attendee_open_id=attendee, display_name=attendee)

    if not attendees:
        raise FeishuSkillError("At least one attendee is required")

    state = MeetingNegotiationState(
        negotiation_id=uuid.uuid4().hex,
        title=title.strip(),
        initiator_open_id=initiator_open_id.strip(),
        timezone=timezone,
        duration_minutes=duration_minutes,
        max_rounds=max(max_rounds, 1),
        current_round=1,
        candidate_slots=slots,
        attendees=attendees,
    )
    return state.to_dict()


def _build_round_prompt(state: MeetingNegotiationState, attendee_open_id: str) -> str:
    options = "\n".join(f"- {datetime.fromisoformat(slot).strftime('%Y-%m-%d %H:%M')}" for slot in state.candidate_slots)
    return (
        f"Round {state.current_round}/{state.max_rounds}: Please confirm your available slots for '{state.title}'\n"
        f"Timezone: {state.timezone}\n"
        f"Options:\n{options}\n"
        "Reply with all available options."
    )


def next_round_prompts(state_payload: dict[str, Any]) -> dict[str, Any]:
    state = _deserialize_negotiation_state(state_payload)
    prompts: list[dict[str, str]] = []
    for attendee in state.attendees.values():
        if state.current_round in attendee.rounds_responded:
            continue
        prompts.append(
            {
                "attendee_open_id": attendee.attendee_open_id,
                "display_name": attendee.display_name,
                "prompt": _build_round_prompt(state, attendee.attendee_open_id),
            }
        )
    return {"negotiation_id": state.negotiation_id, "round": state.current_round, "prompts": prompts}


def submit_attendee_response(
    state_payload: dict[str, Any],
    *,
    attendee_open_id: str,
    accepted_slots: list[str],
    declined_slots: list[str] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    state = _deserialize_negotiation_state(state_payload)
    attendee_id = attendee_open_id.strip()
    attendee = state.attendees.get(attendee_id)
    if attendee is None:
        raise FeishuSkillError("attendee_open_id is not part of this negotiation", payload={"attendee_open_id": attendee_id})

    accepted = {_to_slot_key(slot, state.timezone) for slot in accepted_slots}
    declined = {_to_slot_key(slot, state.timezone) for slot in (declined_slots or [])}
    invalid = [slot for slot in accepted if slot not in state.candidate_slots]
    if invalid:
        raise FeishuSkillError("accepted_slots must be within candidate_slots", payload={"invalid_slots": invalid})

    attendee.accepted_slots.update(accepted)
    attendee.declined_slots.update(declined)
    attendee.rounds_responded.add(state.current_round)
    if note:
        attendee.notes.append(note)

    votes: dict[str, int] = {slot: 0 for slot in state.candidate_slots}
    all_responded = True
    for item in state.attendees.values():
        if state.current_round not in item.rounds_responded:
            all_responded = False
        for slot in item.accepted_slots:
            if slot in votes:
                votes[slot] += 1

    attendee_count = len(state.attendees)
    agreed_slot: str | None = None
    for slot in state.candidate_slots:
        if votes.get(slot, 0) == attendee_count:
            agreed_slot = slot
            break

    if agreed_slot:
        state.agreed_slot = agreed_slot
        state.status = "agreed"
    elif all_responded and state.current_round >= state.max_rounds:
        state.status = "failed"
    elif all_responded:
        state.current_round += 1

    return {
        "state": state.to_dict(),
        "votes": votes,
        "all_responded": all_responded,
        "agreed_slot": agreed_slot,
    }


def send_final_invitations(
    *,
    attendee_open_ids: list[str],
    title: str,
    start_time: str,
    end_time: str,
    timezone: str,
    meeting_link: str | None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    message = (
        f"会议确认: {title}\n"
        f"时间: {start_time} - {end_time} ({timezone})\n"
        f"链接: {meeting_link or '请查看日历邀请'}"
    )
    content = json.dumps({"text": message}, ensure_ascii=False)
    delivered: list[str] = []
    failed: list[dict[str, str]] = []

    for attendee_open_id in attendee_open_ids:
        target = attendee_open_id.strip()
        if not target:
            continue
        try:
            _openapi_request(
                "POST",
                "/open-apis/im/v1/messages",
                params={"receive_id_type": "open_id"},
                body={"receive_id": target, "msg_type": "text", "content": content},
                session=session,
            )
            delivered.append(target)
        except FeishuSkillError as exc:
            failed.append({"attendee_open_id": target, "error": str(exc)})

    return {"delivered": delivered, "failed": failed}


def finalize_negotiation_and_create_meeting(
    state_payload: dict[str, Any],
    *,
    description: str | None = None,
    location: str | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    state = _deserialize_negotiation_state(state_payload)
    if state.status != "agreed" or not state.agreed_slot:
        raise FeishuSkillError("negotiation has not reached an agreement", payload=state.to_dict())

    start_dt = datetime.fromisoformat(state.agreed_slot)
    end_dt = datetime.fromtimestamp(start_dt.timestamp() + state.duration_minutes * 60, tz=start_dt.tzinfo)
    attendee_open_ids = sorted(set(state.attendees.keys()))
    participant_open_ids = sorted(set(attendee_open_ids + [state.initiator_open_id]))

    created_meetings: list[dict[str, Any]] = []
    for calendar_owner_open_id in participant_open_ids:
        calendar_id = _primary_calendar_id_for_user(calendar_owner_open_id, session=session)
        meeting = create_meeting(
            title=state.title,
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat(),
            attendees=participant_open_ids,
            timezone=state.timezone,
            description=description,
            location=location,
            initiator_open_id=state.initiator_open_id,
            initiator_calendar_id=calendar_id,
            session=session,
        )
        created_meetings.append(
            {
                "calendar_owner_open_id": calendar_owner_open_id,
                "meeting": meeting,
            }
        )

    primary_meeting = next(
        (item["meeting"] for item in created_meetings if item["calendar_owner_open_id"] == state.initiator_open_id),
        created_meetings[0]["meeting"],
    )

    invitation = send_final_invitations(
        attendee_open_ids=attendee_open_ids,
        title=state.title,
        start_time=start_dt.strftime("%Y-%m-%d %H:%M"),
        end_time=end_dt.strftime("%Y-%m-%d %H:%M"),
        timezone=state.timezone,
        meeting_link=primary_meeting.get("join_url"),
        session=session,
    )

    return {
        "negotiation_id": state.negotiation_id,
        "agreed_slot": state.agreed_slot,
        "meeting_owner_open_id": state.initiator_open_id,
        "primary_meeting": primary_meeting,
        "meetings": created_meetings,
        "invitation_delivery": invitation,
    }


def _resolve_meeting_attendees(attendees: list[Any], *, session: requests.Session | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    attendee_results: list[dict[str, Any]] = []
    resolved_attendees: list[dict[str, Any]] = []
    warnings: list[str] = []

    for raw_item in attendees:
        spec = _normalize_attendee_spec(raw_item)
        requested = spec["open_id"] or spec["email"] or spec["name"] or str(raw_item)
        if spec["open_id"]:
            resolved_attendees.append({"type": "user", "user_id": spec["open_id"], "is_optional": False})
            attendee_results.append({
                "requested": requested,
                "status": "resolved",
                "display_name": spec["name"],
                "open_id": spec["open_id"],
                "match_reason": "provided_open_id",
            })
            continue

        if spec["email"]:
            candidate = _resolve_email_attendee(spec["email"], session=session)
            if candidate is None:
                attendee_results.append({
                    "requested": requested,
                    "status": "unresolved",
                    "error": "email_not_found",
                })
                continue
            resolved_attendees.append({"type": "user", "user_id": candidate["open_id"], "is_optional": False})
            attendee_results.append({
                "requested": requested,
                "status": "resolved",
                "display_name": candidate["display_name"],
                "open_id": candidate["open_id"],
                "match_reason": candidate["match_reason"],
            })
            continue

        normalized_name = str(spec["name"] or "").strip()
        if "群" in normalized_name:
            try:
                group_results, group_attendees = _resolve_group_phrase_attendees(normalized_name, session=session)
            except FeishuSkillError as exc:
                attendee_results.append(
                    {
                        "requested": requested,
                        "status": "unresolved",
                        "error": "group_lookup_failed",
                        "details": str(exc),
                    }
                )
                continue
            attendee_results.extend(group_results)
            resolved_attendees.extend(group_attendees)
            continue

        search_result = search_contacts(str(spec["name"] or ""), limit=5, session=session)
        candidates = search_result["candidates"]
        if not candidates:
            attendee_results.append({
                "requested": requested,
                "status": "unresolved",
                "error": "name_not_found",
            })
            continue
        top_candidate = candidates[0]
        if len(candidates) == 1 or top_candidate["score"] >= 1.0:
            resolved_attendees.append({"type": "user", "user_id": top_candidate["open_id"], "is_optional": False})
            attendee_results.append({
                "requested": requested,
                "status": "resolved",
                "display_name": top_candidate["display_name"],
                "open_id": top_candidate["open_id"],
                "match_reason": top_candidate["match_reason"],
            })
            continue
        warnings.append(f"Ambiguous attendee '{requested}' matched {len(candidates)} contacts")
        attendee_results.append({
            "requested": requested,
            "status": "ambiguous",
            "display_name": top_candidate["display_name"],
            "open_id": top_candidate["open_id"],
            "match_reason": top_candidate["match_reason"],
            "error": "ambiguous_name",
        })

    deduped_attendees: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in resolved_attendees:
        user_id = str(item.get("user_id") or "").strip()
        if not user_id or user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        deduped_attendees.append(item)

    return attendee_results, deduped_attendees, warnings


def create_meeting(
    *,
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[Any],
    timezone: str = DEFAULT_TIMEZONE,
    description: str | None = None,
    location: str | None = None,
    idempotency_key: str | None = None,
    initiator_open_id: str | None = None,
    initiator_calendar_id: str | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    start_dt = _parse_time(start_time, timezone)
    end_dt = _parse_time(end_time, timezone)
    if end_dt <= start_dt:
        raise FeishuSkillError("end_time must be later than start_time")

    attendee_results, resolved_attendees, warnings = _resolve_meeting_attendees(attendees, session=session)
    unresolved = [item for item in attendee_results if item["status"] != "resolved"]
    if unresolved:
        raise FeishuSkillError(
            "Not all attendees could be resolved",
            payload={"attendee_results": attendee_results, "warnings": warnings},
        )

    if initiator_calendar_id:
        calendar_id = initiator_calendar_id.strip()
    elif initiator_open_id:
        calendar_id = _primary_calendar_id_for_user(initiator_open_id, session=session)
    else:
        calendar_id = _primary_calendar_id(session=session)

    payload: dict[str, Any] = {
        "summary": title,
        "description": description or "",
        "need_notification": True,
        "start_time": _build_time_info(start_dt, timezone),
        "end_time": _build_time_info(end_dt, timezone),
        "attendees": resolved_attendees,
        "vchat": {"vc_type": "vc"},
    }
    if location:
        payload["location"] = {"name": location}

    params: dict[str, Any] = {"user_id_type": "open_id"}
    if idempotency_key:
        params["idempotency_key"] = idempotency_key

    data = _openapi_request(
        "POST",
        f"/open-apis/calendar/v4/calendars/{calendar_id}/events",
        params=params,
        body=payload,
        session=session,
    )
    event = data.get("event") if isinstance(data.get("event"), dict) else {}
    vchat = event.get("vchat") if isinstance(event.get("vchat"), dict) else {}
    event_id = str(event.get("event_id") or "").strip()
    if not event_id:
        raise FeishuSkillError("Meeting creation response did not include event_id", payload=data)
    return {
        "event_id": event_id,
        "organizer_identity": DEFAULT_ORGANIZER_IDENTITY,
        "initiator_open_id": initiator_open_id,
        "calendar_id": str(event.get("organizer_calendar_id") or calendar_id),
        "join_url": str(vchat.get("meeting_url") or vchat.get("live_link") or "").strip() or None,
        "attendee_results": attendee_results,
        "warnings": warnings,
    }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Feishu bot meeting helper for the feishu-bot-meeting-coordinator skill")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_search_parser = subparsers.add_parser("search-chats")
    chat_search_parser.add_argument("--query", required=True)
    chat_search_parser.add_argument("--limit", type=int, default=10)

    chat_members_parser = subparsers.add_parser("get-chat-members")
    chat_members_parser.add_argument("--chat-id", required=True)

    search_parser = subparsers.add_parser("search-contacts")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=10)

    meeting_parser = subparsers.add_parser("create-meeting")
    meeting_parser.add_argument("--title", required=True)
    meeting_parser.add_argument("--start-time", required=True)
    meeting_parser.add_argument("--end-time", required=True)
    meeting_parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    meeting_parser.add_argument("--attendee", action="append", dest="attendees", required=True)
    meeting_parser.add_argument("--description")
    meeting_parser.add_argument("--location")
    meeting_parser.add_argument("--idempotency-key")
    meeting_parser.add_argument("--initiator-open-id")
    meeting_parser.add_argument("--initiator-calendar-id")

    negotiation_parser = subparsers.add_parser("start-negotiation")
    negotiation_parser.add_argument("--title", required=True)
    negotiation_parser.add_argument("--initiator-open-id", required=True)
    negotiation_parser.add_argument("--duration-minutes", type=int, required=True)
    negotiation_parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    negotiation_parser.add_argument("--max-rounds", type=int, default=DEFAULT_NEGOTIATION_ROUNDS)
    negotiation_parser.add_argument("--attendee-open-id", action="append", required=True, dest="attendee_open_ids")
    negotiation_parser.add_argument("--candidate-slot", action="append", required=True, dest="candidate_slots")

    submit_parser = subparsers.add_parser("submit-response")
    submit_parser.add_argument("--state-json", required=True)
    submit_parser.add_argument("--attendee-open-id", required=True)
    submit_parser.add_argument("--accepted-slot", action="append", required=True, dest="accepted_slots")
    submit_parser.add_argument("--declined-slot", action="append", dest="declined_slots")
    submit_parser.add_argument("--note")

    finalize_parser = subparsers.add_parser("finalize-negotiation")
    finalize_parser.add_argument("--state-json", required=True)
    finalize_parser.add_argument("--description")
    finalize_parser.add_argument("--location")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli()
    args = parser.parse_args(argv)
    try:
        if args.command == "search-chats":
            result = search_chats(args.query, limit=args.limit)
        elif args.command == "get-chat-members":
            result = get_chat_members(args.chat_id)
        elif args.command == "search-contacts":
            result = search_contacts(args.query, limit=args.limit)
        elif args.command == "create-meeting":
            result = create_meeting(
                title=args.title,
                start_time=args.start_time,
                end_time=args.end_time,
                attendees=list(args.attendees or []),
                timezone=args.timezone,
                description=args.description,
                location=args.location,
                idempotency_key=args.idempotency_key,
                initiator_open_id=args.initiator_open_id,
                initiator_calendar_id=args.initiator_calendar_id,
            )
        elif args.command == "start-negotiation":
            result = start_negotiation(
                title=args.title,
                initiator_open_id=args.initiator_open_id,
                attendee_open_ids=list(args.attendee_open_ids or []),
                candidate_slots=list(args.candidate_slots or []),
                duration_minutes=args.duration_minutes,
                timezone=args.timezone,
                max_rounds=args.max_rounds,
            )
        elif args.command == "submit-response":
            state_payload = json.loads(args.state_json)
            result = submit_attendee_response(
                state_payload,
                attendee_open_id=args.attendee_open_id,
                accepted_slots=list(args.accepted_slots or []),
                declined_slots=list(args.declined_slots or []),
                note=args.note,
            )
        else:
            state_payload = json.loads(args.state_json)
            result = finalize_negotiation_and_create_meeting(
                state_payload,
                description=args.description,
                location=args.location,
            )
    except FeishuSkillError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "payload": exc.payload}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
