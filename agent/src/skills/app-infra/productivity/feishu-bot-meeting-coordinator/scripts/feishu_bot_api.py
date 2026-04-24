from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_ORGANIZER_IDENTITY = "semantier"
DEFAULT_CONTACT_SCOPE = "contacts-added-to-bot"


class FeishuSkillError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = payload or {}


def _env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise FeishuSkillError(f"Missing required environment variable: {name}")
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

    return attendee_results, resolved_attendees, warnings


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
        "calendar_id": str(event.get("organizer_calendar_id") or calendar_id),
        "join_url": str(vchat.get("meeting_url") or vchat.get("live_link") or "").strip() or None,
        "attendee_results": attendee_results,
        "warnings": warnings,
    }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Feishu bot meeting helper for the feishu-bot-meeting-coordinator skill")
    subparsers = parser.add_subparsers(dest="command", required=True)

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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli()
    args = parser.parse_args(argv)
    try:
        if args.command == "search-contacts":
            result = search_contacts(args.query, limit=args.limit)
        else:
            result = create_meeting(
                title=args.title,
                start_time=args.start_time,
                end_time=args.end_time,
                attendees=list(args.attendees or []),
                timezone=args.timezone,
                description=args.description,
                location=args.location,
                idempotency_key=args.idempotency_key,
            )
    except FeishuSkillError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "payload": exc.payload}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
