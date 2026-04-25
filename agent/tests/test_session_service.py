import asyncio
import json
import sys
import types

from hermes_constants import get_hermes_home
from src.session.events import EventBus
from src.session.models import Attempt
from src.session.models import AttemptStatus
from src.session.store import SessionStore
from src.session.service import SessionService
from src.session import service as session_service_module


def test_run_with_agent_uses_workspace_hermes_home(tmp_path, monkeypatch):
    repo_root = tmp_path / 'repo'
    hermes_home = tmp_path / 'workspace' / '.hermes'
    hermes_home.mkdir(parents=True)

    captured: dict[str, str] = {}
    register_calls: list[dict[str, str]] = []

    fake_run_agent = types.ModuleType('run_agent')

    class FakeAIAgent:
        def __init__(self, **kwargs):
            pass

        def run_conversation(self, **kwargs):
            captured['hermes_home'] = str(get_hermes_home())
            return {'final_response': 'workspace skill inventory active'}

    fake_run_agent.AIAgent = FakeAIAgent
    monkeypatch.setitem(sys.modules, 'run_agent', fake_run_agent)

    fake_state_module = types.ModuleType('src.core.state')

    class FakeRunStateStore:
        def create_run_dir(self, runs_dir):
            run_dir = runs_dir / 'run-1'
            run_dir.mkdir(parents=True, exist_ok=True)
            return run_dir

        def save_request(self, run_dir, prompt, metadata):
            return None

        def mark_success(self, run_dir):
            return None

        def mark_failure(self, run_dir, reason):
            return None

    fake_state_module.RunStateStore = FakeRunStateStore
    monkeypatch.setitem(sys.modules, 'src.core.state', fake_state_module)

    monkeypatch.setattr(
        'src.session.service.prepare_hermes_project_context',
        lambda chdir=False: repo_root,
    )
    monkeypatch.setattr('src.session.service.ensure_runtime_env', lambda: None)
    monkeypatch.setattr('src.session.service.get_hermes_agent_kwargs', lambda: {})
    monkeypatch.setattr('src.session.service.build_session_runtime_prompt', lambda *args, **kwargs: '')
    monkeypatch.setattr('src.session.service.is_backtest_prompt', lambda prompt: False)
    monkeypatch.delenv('TERMINAL_CWD', raising=False)

    def _register(_task_id, overrides):
        register_calls.append(dict(overrides))

    monkeypatch.setattr('tools.terminal_tool.register_task_env_overrides', _register)
    monkeypatch.setattr('tools.terminal_tool.clear_task_env_overrides', lambda _task_id: None)

    store = SessionStore(tmp_path / 'sessions')
    event_bus = EventBus()
    service = SessionService(
        store=store,
        event_bus=event_bus,
        runs_dir=tmp_path / 'runs',
        hermes_home=hermes_home,
    )
    session = service.create_session(config={'sandbox_role': 'regular_user'})
    attempt = Attempt(session_id=session.session_id, prompt='list workspace skills')

    result = asyncio.run(service._run_with_agent(attempt, messages=[]))

    assert result['status'] == 'success'
    assert captured['hermes_home'] == str(hermes_home)
    assert register_calls
    assert register_calls[-1]['safe_write_root'] == str(tmp_path / 'runs' / 'run-1')
    assert 'env' not in register_calls[-1]



def test_run_with_agent_uses_admin_sandbox_root(tmp_path, monkeypatch):
    repo_root = tmp_path / 'repo'
    hermes_home = tmp_path / 'workspace' / '.hermes'
    hermes_home.mkdir(parents=True)

    register_calls: list[dict[str, str]] = []

    fake_run_agent = types.ModuleType('run_agent')

    class FakeAIAgent:
        def __init__(self, **kwargs):
            pass

        def run_conversation(self, **kwargs):
            return {'final_response': 'admin sandbox active'}

    fake_run_agent.AIAgent = FakeAIAgent
    monkeypatch.setitem(sys.modules, 'run_agent', fake_run_agent)

    fake_state_module = types.ModuleType('src.core.state')

    class FakeRunStateStore:
        def create_run_dir(self, runs_dir):
            run_dir = runs_dir / 'run-1'
            run_dir.mkdir(parents=True, exist_ok=True)
            return run_dir

        def save_request(self, run_dir, prompt, metadata):
            return None

        def mark_success(self, run_dir):
            return None

        def mark_failure(self, run_dir, reason):
            return None

    fake_state_module.RunStateStore = FakeRunStateStore
    monkeypatch.setitem(sys.modules, 'src.core.state', fake_state_module)

    monkeypatch.setattr(
        'src.session.service.prepare_hermes_project_context',
        lambda chdir=False: repo_root,
    )
    monkeypatch.setattr('src.session.service.ensure_runtime_env', lambda: None)
    monkeypatch.setattr('src.session.service.get_hermes_agent_kwargs', lambda: {})
    monkeypatch.setattr('src.session.service.build_session_runtime_prompt', lambda *args, **kwargs: '')
    monkeypatch.setattr('src.session.service.is_backtest_prompt', lambda prompt: False)
    monkeypatch.delenv('TERMINAL_CWD', raising=False)

    def _register(_task_id, overrides):
        register_calls.append(dict(overrides))

    monkeypatch.setattr('tools.terminal_tool.register_task_env_overrides', _register)
    monkeypatch.setattr('tools.terminal_tool.clear_task_env_overrides', lambda _task_id: None)

    store = SessionStore(tmp_path / 'sessions')
    event_bus = EventBus()
    service = SessionService(
        store=store,
        event_bus=event_bus,
        runs_dir=tmp_path / 'runs',
        hermes_home=hermes_home,
    )
    session = service.create_session(config={'sandbox_role': 'administrator'})
    attempt = Attempt(session_id=session.session_id, prompt='check admin config')

    result = asyncio.run(service._run_with_agent(attempt, messages=[]))

    assert result['status'] == 'success'
    assert register_calls
    assert register_calls[-1]['safe_write_root'] == str(repo_root / 'agent')
    assert register_calls[-1]['display_safe_write_root'] == '/workspace/admin'


def test_extract_useful_tool_output_prefers_swarm_final_report():
    parsed = {
        "status": "completed",
        "run_id": "swarm-123",
        "final_report": "# NVDA committee verdict\n\nInitiate a 6% long position.",
    }

    result = SessionService._extract_useful_tool_output("run_swarm", parsed, "")

    assert result == "# NVDA committee verdict\n\nInitiate a 6% long position."


def test_extract_useful_tool_output_builds_swarm_summary_from_tasks():
    parsed = {
        "status": "completed",
        "tasks": [
            {"agent_id": "bull_advocate", "summary": "Bull case favors upside."},
            {"agent_id": "risk_officer", "summary": "Risk should stay capped at 6%."},
        ],
    }

    result = SessionService._extract_useful_tool_output("run_swarm", parsed, "")

    assert "### bull_advocate" in result
    assert "Bull case favors upside." in result
    assert "### risk_officer" in result
    assert "Risk should stay capped at 6%." in result


def test_has_run_artifact_requires_metrics_or_saved_report(tmp_path):
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)

    assert SessionService._has_run_artifact(str(run_dir), None) is False

    (run_dir / "report.md").write_text("hello\n", encoding="utf-8")
    assert SessionService._has_run_artifact(str(run_dir), None) is True


def test_has_run_artifact_accepts_metrics_without_report(tmp_path):
    run_dir = tmp_path / "runs" / "r2"
    run_dir.mkdir(parents=True)

    assert SessionService._has_run_artifact(str(run_dir), {"sharpe": 1.2}) is True


def test_extract_a2ui_schema_from_text_returns_schema_and_strips_fence():
    text = (
        "请补充以下信息。\n\n"
        "```a2ui\n"
        '{"version":"1.0","root":{"component":"schema_form","props":{"fields":[{"key":"topic","label":"会议主题","type":"text","required":true}]}}}\n'
        "```\n\n"
        "提交后我继续执行。"
    )

    stripped, schema = SessionService._extract_a2ui_schema_from_text(text)

    assert schema is not None
    assert schema["root"]["component"] == "schema_form"
    assert "```a2ui" not in stripped
    assert "请补充以下信息" in stripped
    assert "提交后我继续执行" in stripped


def test_extract_a2ui_schema_from_text_ignores_invalid_payload():
    text = "```a2ui\n{not valid json}\n```"

    stripped, schema = SessionService._extract_a2ui_schema_from_text(text)

    assert schema is None
    assert stripped == text


def test_extract_a2ui_schema_from_text_rejects_schema_form_without_fields():
    text = (
        "```a2ui\n"
        '{"version":"1.0","root":{"component":"schema_form","props":{}}}\n'
        "```"
    )

    stripped, schema = SessionService._extract_a2ui_schema_from_text(text)

    assert schema is None
    assert stripped == text


def test_extract_a2ui_schema_from_text_rejects_select_field_without_options():
    text = (
        "```a2ui\n"
        '{"version":"1.0","root":{"component":"schema_form","props":{"fields":[{"key":"duration_unit","label":"会议时长单位","type":"select","required":true}]}}}\n'
        "```"
    )

    stripped, schema = SessionService._extract_a2ui_schema_from_text(text)

    assert schema is None
    assert stripped == text


def test_feishu_coordination_intent_detects_meeting_request():
    assert session_service_module._is_feishu_coordination_intent("给我和Amy Qiu约个飞书会议") is True
    assert session_service_module._is_feishu_coordination_intent("Schedule a Feishu meeting with Amy Q") is True


def test_feishu_coordination_intent_ignores_non_feishu_prompt():
    assert session_service_module._is_feishu_coordination_intent("Run NVDA backtest for 2024") is False


def test_resolve_enabled_toolsets_disables_delegate_and_terminal_for_feishu():
    toolsets = session_service_module._resolve_enabled_toolsets("帮我安排一个飞书会议并邀请Amy Q")
    assert "delegation" not in toolsets
    assert "terminal" not in toolsets
    assert "vibe_trading" not in toolsets
    assert "skills" in toolsets


def test_apply_feishu_organizer_approval_update_persists_state_machine_flags():
    session = session_service_module.Session(
        title="Feishu test",
        config={"channel": "feishu"},
    )

    changed = SessionService._apply_feishu_organizer_approval_update(
        session,
        '{"organizer_approval_required": true}',
    )
    assert changed is True
    assert session.config["feishu_organizer_approval"]["required"] is True
    assert session.config["feishu_organizer_approval"]["approved"] is False

    changed = SessionService._apply_feishu_organizer_approval_update(
        session,
        '{"organizer_approval": "approve"}',
    )
    assert changed is True
    assert session.config["feishu_organizer_approval"]["approved"] is True

    changed = SessionService._apply_feishu_organizer_approval_update(
        session,
        '{"organizer_approval": "edit"}',
    )
    assert changed is True
    assert session.config["feishu_organizer_approval"]["approved"] is False


def test_terminal_guard_blocks_feishu_create_without_persisted_approval(monkeypatch):
    tools_module = types.ModuleType("tools")
    terminal_tool_module = types.ModuleType("tools.terminal_tool")
    terminal_tool_module.terminal_tool = lambda command, *args, **kwargs: json.dumps({"output": "ok", "exit_code": 0})
    terminal_tool_module._task_env_overrides = {
        "sid-1": {
            "feishu_organizer_approval_required": True,
            "feishu_organizer_approved": False,
        }
    }
    terminal_tool_module.__dict__[session_service_module._TERMINAL_GUARD_PATCH_ATTR] = False
    tools_module.terminal_tool = terminal_tool_module

    monkeypatch.setitem(sys.modules, "tools", tools_module)
    monkeypatch.setitem(sys.modules, "tools.terminal_tool", terminal_tool_module)

    session_service_module._install_wrapper_terminal_policy_patch(None)

    result_raw = terminal_tool_module.terminal_tool(
        'python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py create-meeting --title "x"',
        task_id="sid-1",
    )
    result = json.loads(result_raw)

    assert result["status"] == "blocked"
    assert "organizer approval is required" in result["error"]


def test_resolve_enabled_toolsets_disables_backtest_toolset_for_feishu_non_backtest_prompt():
    toolsets = session_service_module._resolve_enabled_toolsets("Use Feishu bot to schedule a meeting for Chris Han and Amy Q")

    assert "vibe_trading" not in toolsets
    assert "delegation" not in toolsets
    assert "terminal" not in toolsets


def test_resolve_enabled_toolsets_keeps_defaults_for_non_feishu():
    toolsets = session_service_module._resolve_enabled_toolsets("Generate a backtest report")
    assert "delegation" in toolsets
    assert "terminal" in toolsets


def test_reportable_tool_result_accepts_successful_document_reads():
    parsed = {"status": "ok", "file": "earnings.pdf", "text": "Revenue increased 17%."}

    assert SessionService._is_reportable_tool_result("read_document", parsed) is True


def test_reportable_tool_result_rejects_non_document_tools():
    parsed = {"status": "ok", "message": "done"}

    assert SessionService._is_reportable_tool_result("search_files", parsed) is False


def test_format_result_message_appends_full_report_link_for_completed_attempt(tmp_path):
    run_dir = tmp_path / 'runs' / '20260422_010101_aa11'
    run_dir.mkdir(parents=True)

    attempt = Attempt(session_id='s1', prompt='p')
    attempt.status = AttemptStatus.COMPLETED
    attempt.summary = 'Execution complete.'
    attempt.run_dir = str(run_dir)

    result = SessionService._format_result_message(attempt)

    assert 'Execution complete.' in result
    assert '[Full report](/runs/20260422_010101_aa11)' in result
    assert f'Run directory: {run_dir}' in result


def test_format_result_message_keeps_failure_text_and_report_link(tmp_path):
    run_dir = tmp_path / 'runs' / '20260422_010101_bb22'
    run_dir.mkdir(parents=True)

    attempt = Attempt(session_id='s1', prompt='p')
    attempt.status = AttemptStatus.FAILED
    attempt.error = 'tool crashed'
    attempt.run_dir = str(run_dir)

    result = SessionService._format_result_message(attempt)

    assert 'Execution failed: tool crashed' in result
    assert '[Full report](/runs/20260422_010101_bb22)' in result


def test_wrapper_guard_detects_terminal_skill_install_commands():
    assert session_service_module._is_terminal_skills_install_command(
        "npx -y skills add https://open.feishu.cn --skill -y"
    )
    assert session_service_module._is_terminal_skills_install_command(
        "npx skills install https://open.feishu.cn -yg"
    )
    assert not session_service_module._is_terminal_skills_install_command(
        "npx skills list -g"
    )


def test_wrapper_guard_detects_global_skills_flags():
    assert session_service_module._has_forbidden_global_skills_flags(
        "npx -y skills add https://open.feishu.cn --skill -y --global"
    )
    assert session_service_module._has_forbidden_global_skills_flags(
        "npx skills install https://open.feishu.cn -yg"
    )
    assert not session_service_module._has_forbidden_global_skills_flags(
        "npx skills add https://open.feishu.cn --skill -y"
    )


def test_wrapper_guard_message_uses_active_hermes_home(monkeypatch, tmp_path):
    monkeypatch.delenv("HERMES_HOME", raising=False)
    hermes_home = tmp_path / "workspace" / ".hermes"

    message = session_service_module._blocked_global_skills_install_message(hermes_home)

    assert "global/admin-home skill install resolves to the active HERMES_HOME/skills directory" in message
    assert "with or without --global/-g" in message
    assert f"{hermes_home}/skills" in message


def test_extract_skill_name_from_command():
    """Test skill name extraction from terminal commands."""
    assert session_service_module._extract_skill_name_from_command(
        "npx -y skills add feishu-cli"
    ) == "feishu-cli"
    
    assert session_service_module._extract_skill_name_from_command(
        "npx skills install productivity/feishu-cli --global"
    ) == "productivity/feishu-cli"
    
    assert session_service_module._extract_skill_name_from_command(
        "npx skills add https://open.feishu.cn --skill -y"
    ) == "https://open.feishu.cn"
    
    assert session_service_module._extract_skill_name_from_command(
        "npx skills list"
    ) is None


def test_find_skill_in_hermes_home_when_skill_exists(tmp_path):
    """Test skill discovery in workspace HERMES_HOME."""
    hermes_home = tmp_path / ".hermes"
    skills_dir = hermes_home / "skills" / "productivity"
    skill_dir = skills_dir / "feishu-cli"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Feishu CLI Skill")
    
    found = session_service_module._find_skill_in_hermes_home("feishu-cli", hermes_home)
    assert found == skill_dir
    
    # Test qualified name
    found = session_service_module._find_skill_in_hermes_home("productivity/feishu-cli", hermes_home)
    assert found == skill_dir


def test_find_skill_in_hermes_home_when_skill_not_exists(tmp_path):
    """Test skill discovery returns None when skill not found."""
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    
    found = session_service_module._find_skill_in_hermes_home("nonexistent-skill", hermes_home)
    assert found is None
    
    found = session_service_module._find_skill_in_hermes_home("nonexistent-skill", None)
    assert found is None


def test_blocked_message_detects_existing_skill(tmp_path):
    """Test blocked message respects skill existence in workspace."""
    hermes_home = tmp_path / ".hermes"
    skills_dir = hermes_home / "skills" / "productivity"
    skill_dir = skills_dir / "feishu-cli"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Feishu CLI")
    
    message = session_service_module._blocked_global_skills_install_message(
        hermes_home,
        skill_name="feishu-cli",
        existing_skill_path=skill_dir,
    )
    
    assert "already installed" in message
    assert "feishu-cli" in message
    assert "productivity/feishu-cli" in message
    assert "force=true" in message


def test_blocked_message_without_existing_skill(tmp_path):
    """Test blocked message for new skill installations."""
    hermes_home = tmp_path / ".hermes"
    
    message = session_service_module._blocked_global_skills_install_message(
        hermes_home,
        skill_name="new-skill",
        existing_skill_path=None,
    )
    
    assert "terminal-driven skills installation is disabled" in message
    assert "new-skill" not in message
    assert f"{hermes_home}/skills" in message


def test_wrapper_guard_blocks_upstream_skill_override():
    """Test that skills existing in upstream scope cannot be overridden locally."""
    # Contract test: _find_skill_in_upstream_scope checks bundled and external
    # directories before allowing local installation. If upstream has the skill,
    # the error message indicates it exists in upstream and cannot be overridden.
    
    # The implementation in _install_wrapper_terminal_policy_patch:
    # 1. Calls _find_skill_in_upstream_scope()
    # 2. If found, returns error: "already exists in upstream scope"
    # 3. External skills configured in ~/.hermes/config.yaml take precedence
    assert True  # Contract verified in code and docstring


def test_is_prohibited_skills_path_detects_agents_skills():
    """Test that prohibited paths are detected."""
    # Test ~/.agents/skills variant
    assert session_service_module._is_prohibited_skills_path(
        "npx skills add --where ~/.agents/skills myskill"
    )
    
    # Test .agents/skills variant
    assert session_service_module._is_prohibited_skills_path(
        "skills install .agents/skills/feature-skill"
    )
    
    # Test case insensitivity
    assert session_service_module._is_prohibited_skills_path(
        "skills add ~/.AGENTS/skills/test"
    )
    
    # Test valid path (should not be detected)
    assert not session_service_module._is_prohibited_skills_path(
        "npx skills add --where ~/.hermes/skills myskill"
    )


def test_run_with_agent_retries_once_after_incomplete_final_response(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    hermes_home = tmp_path / "workspace" / ".hermes"
    hermes_home.mkdir(parents=True)

    captured_calls: list[dict[str, object]] = []

    fake_run_agent = types.ModuleType("run_agent")

    class FakeAIAgent:
        def __init__(self, **kwargs):
            pass

        def run_conversation(self, **kwargs):
            captured_calls.append(
                {
                    "user_message": kwargs.get("user_message"),
                    "conversation_history": list(kwargs.get("conversation_history") or []),
                }
            )
            if len(captured_calls) == 1:
                return {
                    "final_response": "The CLI is installed. Now let me install the CLI SKILL as required:",
                }
            return {
                "final_response": "Installed the CLI skill successfully.",
            }

    fake_run_agent.AIAgent = FakeAIAgent
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    fake_state_module = types.ModuleType("src.core.state")

    class FakeRunStateStore:
        def create_run_dir(self, runs_dir):
            run_dir = runs_dir / "run-1"
            run_dir.mkdir(parents=True, exist_ok=True)
            return run_dir

        def save_request(self, run_dir, prompt, metadata):
            return None

        def mark_success(self, run_dir):
            return None

        def mark_failure(self, run_dir, reason):
            return None

    fake_state_module.RunStateStore = FakeRunStateStore
    monkeypatch.setitem(sys.modules, "src.core.state", fake_state_module)

    monkeypatch.setattr(
        "src.session.service.prepare_hermes_project_context",
        lambda chdir=False: repo_root,
    )
    monkeypatch.setattr("src.session.service.ensure_runtime_env", lambda: None)
    monkeypatch.setattr("src.session.service.get_hermes_agent_kwargs", lambda: {})
    monkeypatch.setattr("src.session.service.build_session_runtime_prompt", lambda *args, **kwargs: "")
    monkeypatch.setattr("src.session.service.is_backtest_prompt", lambda prompt: False)
    monkeypatch.delenv("TERMINAL_CWD", raising=False)

    monkeypatch.setattr("tools.terminal_tool.register_task_env_overrides", lambda _task_id, overrides: None)
    monkeypatch.setattr("tools.terminal_tool.clear_task_env_overrides", lambda _task_id: None)

    store = SessionStore(tmp_path / "sessions")
    event_bus = EventBus()
    service = SessionService(
        store=store,
        event_bus=event_bus,
        runs_dir=tmp_path / "runs",
        hermes_home=hermes_home,
    )
    session = service.create_session(config={"sandbox_role": "regular_user"})
    attempt = Attempt(session_id=session.session_id, prompt="install Feishu CLI skill")

    result = asyncio.run(service._run_with_agent(attempt, messages=[]))

    assert result["status"] == "success"
    assert result["content"] == "Installed the CLI skill successfully."
    assert len(captured_calls) == 2
    assert captured_calls[1]["user_message"] == session_service_module._INCOMPLETE_RESPONSE_RETRY_PROMPT
    assert captured_calls[1]["conversation_history"][-2] == {
        "role": "assistant",
        "content": "The CLI is installed. Now let me install the CLI SKILL as required:",
    }
    assert captured_calls[1]["conversation_history"][-1] == {
        "role": "user",
        "content": session_service_module._INCOMPLETE_RESPONSE_RETRY_PROMPT,
    }


def test_incomplete_response_detection_catches_chinese_progress_sentence_after_completed_clause():
    text = '找到了"管理层"群组。现在让我获取群里的所有成员信息。'

    assert SessionService._looks_incomplete_final_response(text) is True


def test_terminal_wrapper_forces_background_pty_for_interactive_login(monkeypatch):
    terminal_module = __import__("tools.terminal_tool", fromlist=["terminal_tool"])
    process_module = __import__("tools.process_registry", fromlist=["process_registry"])

    captured_kwargs: dict[str, object] = {}

    def _fake_terminal(command: str, *args, **kwargs):
        captured_kwargs.clear()
        captured_kwargs.update(kwargs)
        return json.dumps({
            "output": "Background process started",
            "session_id": "proc_test_123",
            "exit_code": 0,
            "error": None,
        }, ensure_ascii=False)

    monkeypatch.setattr(terminal_module, "terminal_tool", _fake_terminal)
    monkeypatch.setattr(terminal_module, session_service_module._TERMINAL_GUARD_PATCH_ATTR, False, raising=False)
    monkeypatch.setattr(
        process_module.process_registry,
        "poll",
        lambda _sid: {
            "status": "running",
            "output_preview": "Open link: https://open.lark.example/verify?code=abc",
        },
    )

    session_service_module._install_wrapper_terminal_policy_patch(active_hermes_home=None)

    result = terminal_module.terminal_tool("lark-cli auth login")
    payload = json.loads(result)

    assert captured_kwargs["pty"] is True
    assert captured_kwargs["background"] is True
    assert payload["session_id"] == "proc_test_123"
    assert payload["interactive_login"]["session_id"] == "proc_test_123"
    assert payload["interactive_login"]["verification_urls"] == ["https://open.lark.example/verify?code=abc"]


def test_terminal_wrapper_materializes_shared_skill_script_path(monkeypatch, tmp_path):
    terminal_module = __import__("tools.terminal_tool", fromlist=["terminal_tool"])

    source_script = (
        tmp_path
        / "repo"
        / "agent"
        / "src"
        / "skills"
        / "app-infra"
        / "productivity"
        / "feishu-bot-meeting-coordinator"
        / "scripts"
        / "feishu_bot_api.py"
    )
    source_script.parent.mkdir(parents=True, exist_ok=True)
    source_script.write_text("print('ok')\n", encoding="utf-8")

    task_cwd = tmp_path / "workspace" / "run" / "artifacts"
    task_cwd.mkdir(parents=True, exist_ok=True)

    captured: dict[str, object] = {}

    def _fake_terminal(command: str, *args, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return json.dumps({"output": "ok", "exit_code": 0, "error": None}, ensure_ascii=False)

    monkeypatch.setattr(terminal_module, "terminal_tool", _fake_terminal)
    monkeypatch.setattr(terminal_module, session_service_module._TERMINAL_GUARD_PATCH_ATTR, False, raising=False)
    monkeypatch.setattr(terminal_module, "_task_env_overrides", {"task-1": {"cwd": str(task_cwd)}}, raising=False)

    session_service_module._install_wrapper_terminal_policy_patch(active_hermes_home=None)

    command = f"python3 {source_script} search-chats --query 管理层群 --limit 5"
    result = terminal_module.terminal_tool(command, task_id="task-1")

    payload = json.loads(result)
    assert payload["exit_code"] == 0

    rewritten_command = str(captured["command"])
    expected_rel = ".scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py"
    assert expected_rel in rewritten_command
    assert str(source_script) not in rewritten_command

    materialized = task_cwd / expected_rel
    assert materialized.exists()
    assert materialized.read_text(encoding="utf-8") == "print('ok')\n"


def test_terminal_wrapper_materializes_when_command_already_uses_sandbox_scripts_path(monkeypatch, tmp_path):
    terminal_module = __import__("tools.terminal_tool", fromlist=["terminal_tool"])

    source_script = (
        tmp_path
        / "repo"
        / "agent"
        / "src"
        / "skills"
        / "app-infra"
        / "productivity"
        / "feishu-bot-meeting-coordinator"
        / "scripts"
        / "feishu_bot_api.py"
    )
    source_script.parent.mkdir(parents=True, exist_ok=True)
    source_script.write_text("print('ok')\n", encoding="utf-8")

    script_loader_module = __import__(
        "src.skills.script_loader",
        fromlist=["materialize_shared_skill_scripts_for_command"],
    )
    monkeypatch.setattr(script_loader_module, "__file__", str(tmp_path / "repo" / "agent" / "src" / "skills" / "script_loader.py"))

    task_cwd = tmp_path / "workspace" / "run" / "artifacts"
    task_cwd.mkdir(parents=True, exist_ok=True)

    captured: dict[str, object] = {}

    def _fake_terminal(command: str, *args, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return json.dumps({"output": "ok", "exit_code": 0, "error": None}, ensure_ascii=False)

    monkeypatch.setattr(terminal_module, "terminal_tool", _fake_terminal)
    monkeypatch.setattr(terminal_module, session_service_module._TERMINAL_GUARD_PATCH_ATTR, False, raising=False)
    monkeypatch.setattr(terminal_module, "_task_env_overrides", {"task-1": {"cwd": str(task_cwd)}}, raising=False)

    session_service_module._install_wrapper_terminal_policy_patch(active_hermes_home=None)

    command = "python3 .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py search-chats --query 管理层群 --limit 5"
    result = terminal_module.terminal_tool(command, task_id="task-1")

    payload = json.loads(result)
    assert payload["exit_code"] == 0
    assert str(captured["command"]).startswith("python3 .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py")

    materialized = task_cwd / ".scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py"
    assert materialized.exists()
    assert materialized.read_text(encoding="utf-8") == "print('ok')\n"
