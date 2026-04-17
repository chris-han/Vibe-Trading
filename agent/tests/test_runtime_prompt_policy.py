from __future__ import annotations

from src import runtime_prompt_policy


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
        "Session workspace: /workspace\n"
        "Run directory: /tmp/run-123\n"
        "Artifacts directory: /tmp/run-123/artifacts\n"
        "Use relative paths or the virtual session paths above for terminal and file operations.\n"
        "Do not rely on host absolute paths.\n"
        "Session: session-abc\n"
    )
    assert runtime_prompt_policy.BACKTEST_WORKFLOW_PROMPT in prompt
    assert runtime_prompt_policy.DOCUMENT_WORKFLOW_PROMPT in prompt
    assert runtime_prompt_policy.MARKET_DATA_WORKFLOW_PROMPT in prompt
    assert runtime_prompt_policy.OUTPUT_FORMAT_PROMPT in prompt
    assert prompt.endswith("skill-body-for:web\n")


def test_build_session_runtime_prompt_uses_requested_channel(monkeypatch):
    seen: list[str] = []

    def _fake_loader(channel: str) -> str:
        seen.append(channel)
        return "skill-body"

    monkeypatch.setattr(runtime_prompt_policy, "load_output_format_skill", _fake_loader)

    runtime_prompt_policy.build_session_runtime_prompt("/tmp/run-1", "session-1", "feishu")

    assert seen == ["feishu"]