from __future__ import annotations

from src import runtime_prompt_policy
from src.upload_capabilities import format_supported_upload_extensions


def test_build_session_runtime_prompt_includes_shared_sections(monkeypatch):
    monkeypatch.setattr(
        runtime_prompt_policy,
        "load_output_format_skill",
        lambda channel: f"skill-body-for:{channel}",
    )

    prompt = runtime_prompt_policy.build_session_runtime_prompt(
        "/tmp/run-123",
        "session-abc",
        "web",
    )

    assert prompt.startswith(
        "Run directory: /tmp/run-123\n"
        "Session workspace: /workspace\n"
        "Artifacts directory: /tmp/run-123/artifacts\n"
        "Uploads directory: /workspace/sessions/session-abc/uploads\n"
        "Use relative paths for terminal work.\n"
        "Use the Uploads directory alias only with file-style tools, not terminal commands.\n"
        "Use /workspace and /workspace/run only as virtual display aliases for file-style tools, not terminal cwd targets.\n"
        "Do not rely on host absolute paths.\n"
        "Session: session-abc\n"
    )
    assert runtime_prompt_policy.BACKTEST_WORKFLOW_PROMPT in prompt
    assert runtime_prompt_policy.DOCUMENT_WORKFLOW_PROMPT in prompt
    assert runtime_prompt_policy.MARKET_DATA_WORKFLOW_PROMPT in prompt
    assert 'skill_view(name="strategy-generate")' in prompt
    assert "Pass config_json and signal_engine_py directly to setup_backtest_run(...)" in prompt
    assert "call skill_view(name=...) first" in prompt
    assert "load_skill(\"strategy-generate\")" not in prompt
    assert "use skill_manage instead of terminal commands or general file-editing tools" in prompt
    assert "if the user asks for a global install, admin-home install, or user-level skill install" in prompt
    assert "active workspace HERMES_HOME/skills directory" in prompt
    assert "file writes to .agents/skills or HERMES_HOME/skills are blocked" in prompt
    assert "Never install skills to `~/.agents/skills`" in prompt
    assert "relative .hermes/skills paths resolve inside the active run/artifacts sandbox" in prompt
    assert "use python3 from the preconfigured session environment" in prompt
    assert "Do NOT assume .venv exists under the current run directory" in prompt
    assert "The terminal already starts inside the run artifacts directory" in prompt
    assert "Treat /workspace and /workspace/run as display aliases for file-style tools" in prompt
    assert "Do NOT cd to /workspace or /workspace/run in terminal commands" in prompt
    assert "use the Hermes web_search tool first" in prompt
    assert "use read_url to fetch the full page content" in prompt
    assert f"Uploaded document types accepted by this runtime: {format_supported_upload_extensions()}." in prompt
    assert 'skill_view(name="ocr-and-documents")' in prompt
    assert "For DOCX, XLSX, or similar local document formats" in prompt
    assert "Never use terminal ls/cd commands against the /workspace upload alias" in prompt
    assert runtime_prompt_policy.OUTPUT_FORMAT_PROMPT in prompt
    assert "```a2ui JSON block" in prompt
    assert "root component 'schema_form'" in prompt
    assert prompt.endswith("skill-body-for:web\n")


def test_build_session_runtime_prompt_uses_requested_channel(monkeypatch):
    seen: list[str] = []

    def _fake_loader(channel: str) -> str:
        seen.append(channel)
        return "skill-body"

    monkeypatch.setattr(runtime_prompt_policy, "load_output_format_skill", _fake_loader)

    runtime_prompt_policy.build_session_runtime_prompt("/tmp/run-1", "session-1", "feishu")

    assert seen == ["feishu"]