from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = (
    REPO_ROOT
    / "agent"
    / "src"
    / "skills"
    / "app-infra"
    / "productivity"
    / "feishu-bot-meeting-coordinator"
)
SKILL_FILE = SKILL_DIR / "SKILL.md"
SCRIPT_FILE = SKILL_DIR / "scripts" / "feishu_bot_api.py"


def _load_helper_module():
    spec = importlib.util.spec_from_file_location("feishu_bot_api", SCRIPT_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_skill_points_to_local_helper_script():
    source = SKILL_FILE.read_text(encoding="utf-8")
    assert 'skill_view(name="feishu-bot-meeting-coordinator", file_path="scripts/feishu_bot_api.py")' in source
    assert "scripts/feishu_bot_api.py" in source
    assert "contact search exposed by the backend" not in source
    assert "meeting creation exposed by the backend" not in source


def test_skill_a2ui_contract_is_mandatory_and_no_bullet_list_fallback():
    """Regression: agent must emit schema_form not a markdown bullet list when fields are missing."""
    source = SKILL_FILE.read_text(encoding="utf-8")
    missing_input_section = source.split("## Pre-Create Review and Approval A2UI Contract", 1)[0]
    # The mandatory enforcement language must be present
    assert "MANDATORY" in source
    # The schema_form component name must appear in the a2ui block
    assert '"component": "schema_form"' in source
    # All required meeting fields must be declared
    for key in ("meeting_title", "meeting_time", "duration_value", "duration_unit", "attendees"):
        assert f'"key": "{key}"' in source
    # The contract must ban the bullet-list pattern explicitly
    assert "free-form" in source or "bullet list" in source or "markdown list" in source
    # duration_unit must be a select with minute/hour options
    assert '"key": "duration_unit"' in source
    assert '"type": "select"' in source
    assert '"value": "分钟"' in source
    assert '"value": "小时"' in source
    assert '"default": "分钟"' not in missing_input_section
    assert "Do not silently assume a default duration" in source
    assert "Never prefill or preselect a required field" in source
    assert "Do not persist confirmation or review forms through file tools" in source
    assert "/tmp/meeting_confirm.md" not in source


def test_skill_requires_organizer_approval_when_organizer_differs_from_requester():
    source = SKILL_FILE.read_text(encoding="utf-8")

    assert "you MAY use that designated organizer" in source
    assert "organizer` and `requester` are not the same person" in source
    assert "MUST obtain explicit approval" in source
    assert "do not create events" in source


def test_skill_defines_pre_create_review_form_with_default_values():
    source = SKILL_FILE.read_text(encoding="utf-8")

    assert "## Pre-Create Review and Approval A2UI Contract" in source
    assert '"title": "确认并审批会议创建"' in source
    assert '"key": "organizer_approval"' in source
    assert '"label": "approve"' in source
    assert '"label": "edit"' in source
    assert '"default": "<resolved_organizer>"' in source
    assert '"default": "<resolved_requester>"' in source


def test_skill_example_state_json_uses_synthetic_ids_and_no_legacy_placeholders():
    source = SKILL_FILE.read_text(encoding="utf-8")

    assert "synthetic fixture" in source
    assert "Never reuse literal" in source
    assert "negotiation_example_001" in source
    assert '"ou_owner"' not in source
    assert '"prop_123abc"' not in source


def test_search_contacts_uses_skill_local_ranking(monkeypatch):
    helper = _load_helper_module()

    mock_data = SimpleNamespace(
        items=[
            SimpleNamespace(name="Amy Q", open_id="ou_amy", email="amy@example.com", en_name=None, enterprise_email=None, avatar=None, department_path=None),
            SimpleNamespace(name="Amy Quinn", open_id="ou_amy_2", email="amy.q@example.com", en_name=None, enterprise_email=None, avatar=None, department_path=None),
            SimpleNamespace(name="Chris Han", open_id="ou_chris", email="chris@example.com", en_name=None, enterprise_email=None, avatar=None, department_path=None),
        ],
        has_more=False,
    )
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data = mock_data

    mock_client = MagicMock()
    mock_client.contact.v3.user.find_by_department.return_value = mock_resp

    monkeypatch.setattr(helper, "_get_client", lambda: mock_client)

    result = helper.search_contacts("Amy Q", limit=2)

    assert result["organizer_identity"] == "semantier"
    assert result["contact_scope"] == "contacts-added-to-bot"
    assert [item["open_id"] for item in result["candidates"]] == ["ou_amy", "ou_amy_2"]
    assert result["candidates"][0]["match_reason"] == "exact_display_name"


def test_cli_exposes_group_lookup_commands():
    helper = _load_helper_module()

    parser = helper._build_cli()

    search_args = parser.parse_args(["search-chats", "--query", "管理层群", "--limit", "5"])
    members_args = parser.parse_args(
        ["get-chat-members", "--chat-id", "oc_abc123", "--member-id-type", "union_id"]
    )

    assert search_args.command == "search-chats"
    assert search_args.query == "管理层群"
    assert search_args.limit == 5
    assert members_args.command == "get-chat-members"
    assert members_args.chat_id == "oc_abc123"
    assert members_args.member_id_type == "union_id"


def test_main_dispatches_group_lookup_commands(monkeypatch, capsys):
    helper = _load_helper_module()

    monkeypatch.setattr(helper, "search_chats", lambda query, limit=10: {"query": query, "limit": limit})

    def fake_get_chat_members(chat_id, member_id_type="open_id"):
        return [{"open_id": "ou_1", "display_name": f"{chat_id}:{member_id_type}"}]

    monkeypatch.setattr(helper, "get_chat_members", fake_get_chat_members)

    exit_code = helper.main(["search-chats", "--query", "管理层群", "--limit", "5"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"ok": true' in output
    assert '"query": "管理层群"' in output

    exit_code = helper.main(["get-chat-members", "--chat-id", "oc_abc123", "--member-id-type", "union_id"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"open_id": "ou_1"' in output
    assert '"display_name": "oc_abc123:union_id"' in output


def test_main_returns_structured_error_for_sdk_exception(monkeypatch, capsys):
    helper = _load_helper_module()

    def raise_skill_error(*args, **kwargs):
        raise helper.FeishuSkillError("invalid chat_id")

    monkeypatch.setattr(helper, "get_chat_members", raise_skill_error)

    exit_code = helper.main(["get-chat-members", "--chat-id", "oc_bad"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert '"ok": false' in output
    assert '"error": "invalid chat_id"' in output


def test_primary_calendar_id_for_user_skips_wrong_user_calendar(monkeypatch):
    helper = _load_helper_module()

    mock_data = SimpleNamespace(
        calendar=None,
        calendars=[
            SimpleNamespace(
                calendar=SimpleNamespace(calendar_id="cal_bot", is_primary=True),
                user_id="ou_bot",
            ),
            SimpleNamespace(
                calendar=SimpleNamespace(calendar_id="cal_target", is_primary=True),
                user_id="ou_target",
            ),
        ],
    )
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data = mock_data

    mock_client = MagicMock()
    mock_client.calendar.v4.calendar.primarys.return_value = mock_resp

    monkeypatch.setattr(helper, "_get_client", lambda: mock_client)

    calendar_id = helper._primary_calendar_id_for_user("ou_target")
    assert calendar_id == "cal_target"


def test_primary_calendar_id_for_user_accepts_calendars_list_shape(monkeypatch):
    helper = _load_helper_module()

    mock_data = SimpleNamespace(
        calendar=None,
        calendars=[
            SimpleNamespace(
                calendar=SimpleNamespace(calendar_id="feishu.cn_test_primary@group.calendar.feishu.cn", is_primary=True),
                user_id="ou_amy",
            )
        ],
    )
    mock_resp = MagicMock()
    mock_resp.success.return_value = True
    mock_resp.data = mock_data

    mock_client = MagicMock()
    mock_client.calendar.v4.calendar.primarys.return_value = mock_resp

    monkeypatch.setattr(helper, "_get_client", lambda: mock_client)

    calendar_id = helper._primary_calendar_id_for_user("ou_amy")

    assert calendar_id == "feishu.cn_test_primary@group.calendar.feishu.cn"


def test_create_meeting_builds_expected_event_payload(monkeypatch):
    helper = _load_helper_module()
    captured: dict[str, object] = {}

    def fake_resolve(attendees):
        assert attendees == ["Chris Han", "Amy Q"]
        return (
            [
                {"requested": "Chris Han", "status": "resolved", "display_name": "Chris Han", "open_id": "ou_chris", "match_reason": "exact_display_name"},
                {"requested": "Amy Q", "status": "resolved", "display_name": "Amy Q", "open_id": "ou_amy", "match_reason": "exact_display_name"},
            ],
            [
                {"type": "user", "user_id": "ou_chris", "is_optional": False},
                {"type": "user", "user_id": "ou_amy", "is_optional": False},
            ],
            [],
        )

    def fake_calendar_id_for_user(user_open_id):
        assert user_open_id == "ou_requester"
        return "cal_primary"

    def capture_create(req):
        captured["req"] = req
        mock_data = SimpleNamespace(
            event=SimpleNamespace(
                event_id="evt_123",
                organizer_calendar_id="cal_primary",
                event_organizer=SimpleNamespace(display_name="Requester Name"),
                vchat=SimpleNamespace(meeting_url="https://meet.example.com/evt_123"),
            )
        )
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data = mock_data
        return mock_resp

    captured_attendee_req: dict[str, object] = {}

    def capture_create_attendee(req):
        captured_attendee_req["req"] = req
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data = SimpleNamespace(attendees=[])
        return mock_resp

    mock_client = MagicMock()
    mock_client.calendar.v4.calendar_event.create = capture_create
    mock_client.calendar.v4.calendar_event_attendee.create = capture_create_attendee

    monkeypatch.setattr(helper, "_resolve_meeting_attendees", fake_resolve)
    monkeypatch.setattr(helper, "_primary_calendar_id_for_user", fake_calendar_id_for_user)
    monkeypatch.setattr(helper, "_get_client", lambda: mock_client)

    result = helper.create_meeting(
        title="项目同步",
        start_time="2026-04-24 15:40",
        end_time="2026-04-24 16:10",
        attendees=["Chris Han", "Amy Q"],
        description="讨论项目进展",
        location="Feishu VC",
        requester_open_id="ou_requester",
    )

    req = captured["req"]
    assert req.http_method.name == "POST"
    assert req.uri == "/open-apis/calendar/v4/calendars/:calendar_id/events"
    assert req.paths == {"calendar_id": "cal_primary"}
    assert [q[0] for q in req.queries] == ["user_id_type"]
    assert req.request_body.summary == "项目同步"
    assert req.request_body.description == "讨论项目进展"
    assert req.request_body.vchat.vc_type == "vc"
    assert req.request_body.location.name == "Feishu VC"
    # Feishu ignores attendees in the create-event body; attendees are added via a separate API.
    assert req.request_body.attendees is None
    # Requester must be set as the event organizer (users can't see the bot's calendar).
    assert req.request_body.event_organizer.user_id == "ou_requester"
    assert req.request_body.event_organizer.display_name == "ou_requester"
    assert result["event_id"] == "evt_123"
    assert result["organizer_identity"] == "Requester Name"
    assert result["calendar_id"] == "cal_primary"
    assert result["join_url"] == "https://meet.example.com/evt_123"

    # Verify attendees were added via the separate attendee API.
    attendee_req = captured_attendee_req["req"]
    attendee_ids = sorted([a.user_id for a in attendee_req.request_body.attendees])
    assert attendee_ids == ["ou_amy", "ou_chris", "ou_requester"]
    assert attendee_req.request_body.need_notification is True


def test_create_meeting_requires_user_owner_context(monkeypatch):
    """Raises when neither requester arg nor FEISHU_REQUESTER_OPEN_ID env var is set."""
    helper = _load_helper_module()

    monkeypatch.setattr(
        helper,
        "_resolve_meeting_attendees",
        lambda attendees: ([], [{"type": "user", "user_id": "ou_a", "is_optional": False}], []),
    )
    monkeypatch.delenv("FEISHU_REQUESTER_OPEN_ID", raising=False)

    with pytest.raises(helper.FeishuSkillError, match="requester_open_id is required"):
        helper.create_meeting(
            title="项目同步",
            start_time="2026-04-24 15:40",
            end_time="2026-04-24 16:10",
            attendees=["ou_a"],
        )


def test_create_meeting_uses_env_requester_as_default(monkeypatch):
    """When no requester arg is given, defaults to FEISHU_REQUESTER_OPEN_ID env var."""
    helper = _load_helper_module()

    monkeypatch.setenv("FEISHU_REQUESTER_OPEN_ID", "ou_requester_env")

    monkeypatch.setattr(
        helper,
        "_resolve_meeting_attendees",
        lambda attendees: (
            [{"status": "resolved", "open_id": "ou_a"}],
            [{"type": "user", "user_id": "ou_a", "is_optional": False}],
            [],
        ),
    )

    def fake_calendar_id_for_user(open_id):
        assert open_id == "ou_requester_env", f"Expected requester open_id, got {open_id!r}"
        return "cal_requester_primary"

    monkeypatch.setattr(helper, "_primary_calendar_id_for_user", fake_calendar_id_for_user)

    def capture_create(req):
        assert req.paths["calendar_id"] == "cal_requester_primary"
        mock_data = SimpleNamespace(
            event=SimpleNamespace(
                event_id="evt_env_001",
                vchat=SimpleNamespace(meeting_url="https://meet.example.com/env"),
            )
        )
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data = mock_data
        return mock_resp

    mock_client = MagicMock()
    mock_client.calendar.v4.calendar_event.create = capture_create

    monkeypatch.setattr(helper, "_get_client", lambda: mock_client)

    result = helper.create_meeting(
        title="默认发起人测试",
        start_time="2026-04-30 10:00",
        end_time="2026-04-30 10:30",
        attendees=["ou_a"],
    )
    assert result["event_id"] == "evt_env_001"
    assert result["requester_open_id"] == "ou_requester_env"


def test_start_negotiation_creates_deterministic_state():
    helper = _load_helper_module()

    state = helper.start_negotiation(
        title="Weekly Sync",
        requester_open_id="ou_requester",
        attendee_open_ids=["ou_a", "ou_b"],
        candidate_slots=["2026-04-24 15:40", "2026-04-24 16:40"],
        duration_minutes=30,
    )

    assert state["title"] == "Weekly Sync"
    assert state["requester_open_id"] == "ou_requester"
    assert state["current_round"] == 1
    assert state["status"] == "negotiating"
    assert sorted(state["attendees"].keys()) == ["ou_a", "ou_b"]
    assert len(state["candidate_slots"]) == 2


def test_submit_attendee_response_reaches_agreement():
    helper = _load_helper_module()

    state = helper.start_negotiation(
        title="Weekly Sync",
        requester_open_id="ou_requester",
        attendee_open_ids=["ou_a", "ou_b"],
        candidate_slots=["2026-04-24 15:40", "2026-04-24 16:40"],
        duration_minutes=30,
    )

    accepted = ["2026-04-24 15:40"]
    result_a = helper.submit_attendee_response(state, attendee_open_id="ou_a", accepted_slots=accepted)
    state_after_a = result_a["state"]
    assert state_after_a["status"] == "negotiating"

    result_b = helper.submit_attendee_response(state_after_a, attendee_open_id="ou_b", accepted_slots=accepted)
    state_after_b = result_b["state"]
    assert state_after_b["status"] == "agreed"
    assert state_after_b["agreed_slot"] is not None


def test_resolve_meeting_attendees_expands_group_phrase(monkeypatch):
    helper = _load_helper_module()

    def fake_resolve_group_phrase_attendees(group_phrase):
        assert group_phrase == "管理层群里的所有人"
        return (
            [
                {
                    "requested": group_phrase,
                    "status": "resolved",
                    "display_name": "Chris Han",
                    "open_id": "ou_chris",
                    "match_reason": "group_member",
                },
                {
                    "requested": group_phrase,
                    "status": "resolved",
                    "display_name": "Amy Q",
                    "open_id": "ou_amy",
                    "match_reason": "group_member",
                },
            ],
            [
                {"type": "user", "user_id": "ou_chris", "is_optional": False},
                {"type": "user", "user_id": "ou_amy", "is_optional": False},
            ],
        )

    monkeypatch.setattr(helper, "_resolve_group_phrase_attendees", fake_resolve_group_phrase_attendees)

    attendee_results, resolved_attendees, warnings = helper._resolve_meeting_attendees(["管理层群里的所有人"])

    assert warnings == []
    assert len(attendee_results) == 2
    assert [item["open_id"] for item in attendee_results] == ["ou_chris", "ou_amy"]
    assert resolved_attendees == [
        {"type": "user", "user_id": "ou_chris", "is_optional": False},
        {"type": "user", "user_id": "ou_amy", "is_optional": False},
    ]


def test_resolve_meeting_attendees_falls_back_to_chat_search_when_name_has_no_group_suffix(monkeypatch):
    """If contact search returns nothing and chat search has a high-confidence match, treat as group."""
    helper = _load_helper_module()

    def fake_search_contacts(query, limit=10):
        return {"query": query, "organizer_identity": "semantier", "contact_scope": "contacts-added-to-bot", "candidates": []}

    def fake_search_chats(query, limit=10):
        return {"query": query, "candidates": [{"chat_id": "oc_mgmt", "name": "管理层", "score": 1.0, "match_reason": "exact_chat_name"}]}

    def fake_resolve_group_phrase_attendees(group_phrase):
        return (
            [{"requested": group_phrase, "status": "resolved", "display_name": "Chris Han", "open_id": "ou_chris", "match_reason": "group_member"}],
            [{"type": "user", "user_id": "ou_chris", "is_optional": False}],
        )

    monkeypatch.setattr(helper, "search_contacts", fake_search_contacts)
    monkeypatch.setattr(helper, "search_chats", fake_search_chats)
    monkeypatch.setattr(helper, "_resolve_group_phrase_attendees", fake_resolve_group_phrase_attendees)

    attendee_results, resolved_attendees, warnings = helper._resolve_meeting_attendees(["管理层"])

    assert warnings == []
    assert len(attendee_results) == 1
    assert attendee_results[0]["open_id"] == "ou_chris"
    assert resolved_attendees == [{"type": "user", "user_id": "ou_chris", "is_optional": False}]


def test_create_meeting_implicitly_adds_requester_when_not_in_attendee_list(monkeypatch):
    """The requester must always be in the attendee list so the event shows on their calendar."""
    helper = _load_helper_module()
    captured: dict[str, object] = {}
    captured_attendee_req: dict[str, object] = {}

    def fake_resolve(attendees):
        return (
            [{"requested": "Amy Q", "status": "resolved", "display_name": "Amy Q", "open_id": "ou_amy", "match_reason": "exact_display_name"}],
            [{"type": "user", "user_id": "ou_amy", "is_optional": False}],
            [],
        )

    def fake_calendar_id_for_user(user_open_id):
        return "cal_requester"

    def capture_create(req):
        captured["req"] = req
        mock_data = SimpleNamespace(
            event=SimpleNamespace(event_id="evt_123", organizer_calendar_id="cal_requester", vchat=SimpleNamespace(meeting_url="https://meet.example.com/evt_123")),
        )
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data = mock_data
        return mock_resp

    def capture_create_attendee(req):
        captured_attendee_req["req"] = req
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data = SimpleNamespace(attendees=[])
        return mock_resp

    mock_client = MagicMock()
    mock_client.calendar.v4.calendar_event.create = capture_create
    mock_client.calendar.v4.calendar_event_attendee.create = capture_create_attendee

    monkeypatch.setattr(helper, "_resolve_meeting_attendees", fake_resolve)
    monkeypatch.setattr(helper, "_primary_calendar_id_for_user", fake_calendar_id_for_user)
    monkeypatch.setattr(helper, "_get_client", lambda: mock_client)

    result = helper.create_meeting(
        title="项目同步",
        start_time="2026-04-24 15:40",
        end_time="2026-04-24 16:10",
        attendees=["Amy Q"],
        requester_open_id="ou_requester",
    )

    # Attendees are not in the create-event body; they are added via a separate API.
    req = captured["req"]
    assert req.request_body.attendees is None
    # Verify attendees were added via the separate attendee API including the implicit requester.
    attendee_req = captured_attendee_req["req"]
    attendee_ids = sorted([a.user_id for a in attendee_req.request_body.attendees])
    assert attendee_ids == ["ou_amy", "ou_requester"]
    assert result["requester_open_id"] == "ou_requester"


def test_finalize_negotiation_creates_meeting_and_sends_invitations(monkeypatch):
    helper = _load_helper_module()
    captured: dict[str, object] = {"create_calls": []}

    def fake_calendar_for_user(user_open_id):
        return f"cal_{user_open_id}"

    def fake_create_meeting(*, title, start_time, end_time, attendees, timezone, description=None, location=None, idempotency_key=None, requester_open_id=None, requester_calendar_id=None):
        captured["create_calls"].append(
            {
                "title": title,
                "attendees": attendees,
                "calendar_id": requester_calendar_id,
                "requester_open_id": requester_open_id,
            }
        )
        return {
            "event_id": f"evt_{requester_calendar_id}",
            "organizer_identity": "semantier",
            "requester_open_id": requester_open_id,
            "calendar_id": requester_calendar_id,
            "join_url": f"https://meet.example.com/{requester_calendar_id}",
            "attendee_results": [],
            "warnings": [],
        }

    def fake_send_final_invitations(*, attendee_open_ids, title, start_time, end_time, timezone, meeting_link):
        captured["notified"] = attendee_open_ids
        captured["meeting_link"] = meeting_link
        return {"delivered": attendee_open_ids, "failed": []}

    monkeypatch.setattr(helper, "create_meeting", fake_create_meeting)
    monkeypatch.setattr(helper, "_primary_calendar_id_for_user", fake_calendar_for_user)
    monkeypatch.setattr(helper, "send_final_invitations", fake_send_final_invitations)

    state = helper.start_negotiation(
        title="Weekly Sync",
        requester_open_id="ou_requester",
        attendee_open_ids=["ou_a", "ou_b"],
        candidate_slots=["2026-04-24 15:40"],
        duration_minutes=30,
    )
    agreed = helper.submit_attendee_response(state, attendee_open_id="ou_a", accepted_slots=["2026-04-24 15:40"])["state"]
    agreed = helper.submit_attendee_response(agreed, attendee_open_id="ou_b", accepted_slots=["2026-04-24 15:40"])["state"]

    result = helper.finalize_negotiation_and_create_meeting(
        agreed,
        description="Discuss milestones",
    )

    assert len(captured["create_calls"]) == 1
    call = captured["create_calls"][0]
    assert call["title"] == "Weekly Sync"
    assert call["attendees"] == ["ou_a", "ou_b", "ou_requester"]
    assert call["requester_open_id"] == "ou_requester"
    assert call["calendar_id"] == "cal_ou_requester"
    assert captured["notified"] == ["ou_a", "ou_b"]
    assert captured["meeting_link"] == "https://meet.example.com/cal_ou_requester"
    assert result["meeting_owner_open_id"] == "ou_requester"
    assert result["primary_meeting"]["calendar_id"] == "cal_ou_requester"
    assert len(result["meetings"]) == 1
