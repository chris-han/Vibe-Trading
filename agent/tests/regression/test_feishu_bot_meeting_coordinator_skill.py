from __future__ import annotations

import importlib.util
from pathlib import Path


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


def test_search_contacts_uses_skill_local_ranking(monkeypatch):
    helper = _load_helper_module()

    def fake_openapi_request(method, path, *, params=None, body=None, session=None):
        assert method == "GET"
        assert path == "/open-apis/contact/v3/users/find_by_department"
        assert params is not None
        assert params["page_size"] == 50
        return {
            "items": [
                {"name": "Amy Q", "open_id": "ou_amy", "email": "amy@example.com"},
                {"name": "Amy Quinn", "open_id": "ou_amy_2", "email": "amy.q@example.com"},
                {"name": "Chris Han", "open_id": "ou_chris", "email": "chris@example.com"},
            ],
            "has_more": False,
        }

    monkeypatch.setattr(helper, "_openapi_request", fake_openapi_request)

    result = helper.search_contacts("Amy Q", limit=2)

    assert result["organizer_identity"] == "semantier"
    assert result["contact_scope"] == "contacts-added-to-bot"
    assert [item["open_id"] for item in result["candidates"]] == ["ou_amy", "ou_amy_2"]
    assert result["candidates"][0]["match_reason"] == "exact_display_name"


def test_tenant_access_token_reads_top_level_field(monkeypatch):
    helper = _load_helper_module()
    captured: dict[str, object] = {}
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret_test")

    def fake_http_json(method, url, *, headers, body=None, params=None, session=None, return_data=True):
        captured["method"] = method
        captured["url"] = url
        captured["return_data"] = return_data
        return {"tenant_access_token": "t-test-token"}

    monkeypatch.setattr(helper, "_http_json", fake_http_json)

    token = helper._tenant_access_token()

    assert token == "t-test-token"
    assert captured["method"] == "POST"
    assert str(captured["url"]).endswith("/open-apis/auth/v3/tenant_access_token/internal")
    assert captured["return_data"] is False


def test_create_meeting_builds_expected_event_payload(monkeypatch):
    helper = _load_helper_module()
    captured: dict[str, object] = {}

    def fake_resolve(attendees, *, session=None):
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

    def fake_calendar_id(*, session=None):
        return "cal_primary"

    def fake_openapi_request(method, path, *, params=None, body=None, session=None):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params
        captured["body"] = body
        return {
            "event": {
                "event_id": "evt_123",
                "organizer_calendar_id": "cal_primary",
                "vchat": {"meeting_url": "https://meet.example.com/evt_123"},
            }
        }

    monkeypatch.setattr(helper, "_resolve_meeting_attendees", fake_resolve)
    monkeypatch.setattr(helper, "_primary_calendar_id", fake_calendar_id)
    monkeypatch.setattr(helper, "_openapi_request", fake_openapi_request)

    result = helper.create_meeting(
        title="项目同步",
        start_time="2026-04-24 15:40",
        end_time="2026-04-24 16:10",
        attendees=["Chris Han", "Amy Q"],
        description="讨论项目进展",
        location="Feishu VC",
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/open-apis/calendar/v4/calendars/cal_primary/events"
    assert captured["params"] == {"user_id_type": "open_id"}
    assert captured["body"]["summary"] == "项目同步"
    assert captured["body"]["description"] == "讨论项目进展"
    assert captured["body"]["vchat"] == {"vc_type": "vc"}
    assert captured["body"]["location"] == {"name": "Feishu VC"}
    assert captured["body"]["attendees"] == [
        {"type": "user", "user_id": "ou_chris", "is_optional": False},
        {"type": "user", "user_id": "ou_amy", "is_optional": False},
    ]
    assert result["event_id"] == "evt_123"
    assert result["calendar_id"] == "cal_primary"
    assert result["join_url"] == "https://meet.example.com/evt_123"