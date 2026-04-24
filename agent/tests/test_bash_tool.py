import json
import subprocess

from src.tools.bash_tool import BashTool, _should_force_pty_for_command


def test_should_force_pty_for_feishu_login_commands() -> None:
    assert _should_force_pty_for_command("lark-cli config init --new")
    assert _should_force_pty_for_command("lark-cli auth login --recommend")
    assert _should_force_pty_for_command("npx @larksuite/cli config init --new")
    assert not _should_force_pty_for_command("echo hello")


def test_should_force_pty_for_generic_interactive_login_commands() -> None:
    assert _should_force_pty_for_command("gh auth login")
    assert _should_force_pty_for_command("firebase login")
    assert _should_force_pty_for_command("mycli oauth start")
    assert _should_force_pty_for_command("tool sso login")


def test_does_not_force_pty_for_non_interactive_auth_queries() -> None:
    assert not _should_force_pty_for_command("gh auth status")
    assert not _should_force_pty_for_command("lark-cli auth status")
    assert not _should_force_pty_for_command("firebase login --help")


def test_timeout_response_keeps_partial_output(monkeypatch) -> None:
    tool = BashTool()

    def _mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=kwargs.get("args", args[0] if args else "cmd"),
            timeout=kwargs.get("timeout", 120),
            output="https://open.feishu.cn/page/cli?user_code=demo",
            stderr="waiting for browser callback",
        )

    monkeypatch.setattr(subprocess, "run", _mock_run)
    payload = json.loads(tool.execute(command="lark-cli auth status", timeout_seconds=3))

    assert payload["status"] == "error"
    assert "timed out" in payload["error"].lower()
    assert "open.feishu.cn/page/cli" in payload["stdout"]
    assert "browser callback" in payload["stderr"]


def test_pty_execution_returns_output() -> None:
    tool = BashTool()
    payload = json.loads(tool.execute(command="printf 'pty-ok'", pty=True, timeout_seconds=5))

    assert payload["status"] == "ok"
    assert payload["used_pty"] is True
    assert "pty-ok" in payload["stdout"]
