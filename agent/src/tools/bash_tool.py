"""Bash tool: execute shell commands under run_dir."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import termios
import time
from typing import Any

from .base import BaseTool

_OUTPUT_LIMIT = 50_000
_DEFAULT_TIMEOUT = 120
_INTERACTIVE_LOGIN_TIMEOUT = 300


def _truncate_output(value: str) -> str:
    return value[:_OUTPUT_LIMIT] if len(value) > _OUTPUT_LIMIT else value


def _decode_timeout_stream(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _tokenize_shell_command(command: str) -> list[str]:
    return [token for token in command.lower().replace("=", " ").split() if token]


def _is_interactive_login_token(token: str) -> bool:
    if token in {"login", "signin", "auth", "oauth", "sso"}:
        return True
    if token.startswith("login:") or token.startswith("signin:"):
        return True
    if token.startswith("auth:") or token.startswith("oauth:"):
        return True
    return token.endswith("-login") or token.endswith("-auth")


def _should_force_pty_for_command(command: str) -> bool:
    normalized = " ".join(command.lower().split())
    if "lark-cli config init --new" in normalized:
        return True
    if "lark-cli auth login" in normalized:
        return True
    if "npx @larksuite/cli config init --new" in normalized:
        return True
    if "npx @larksuite/cli auth login" in normalized:
        return True

    tokens = _tokenize_shell_command(command)
    if not tokens:
        return False

    for idx, token in enumerate(tokens):
        if token.startswith("-"):
            continue
        if not _is_interactive_login_token(token):
            continue

        window = tokens[max(0, idx - 3): min(len(tokens), idx + 4)]
        if any(arg in {"--help", "-h", "help", "status", "list", "whoami", "doctor"} for arg in window):
            continue
        return True

    return False


def _parse_timeout_seconds(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    return min(parsed, 1800)


def _set_pty_size(master_fd: int, rows: int = 24, cols: int = 80) -> None:
    """Set PTY window size so the subprocess sees a real terminal."""
    try:
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except (OSError, IOError):
        pass  # Non-critical: window size hint failed, but PTY still works



class BashTool(BaseTool):
    """Execute shell commands in the working directory."""

    name = "bash"
    description = "Execute a shell command in the working directory. Use for installing packages, running scripts, or inspecting files."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "pty": {
                "type": "boolean",
                "description": "Run command in a pseudo-terminal for interactive CLIs.",
            },
            "timeout_seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1800,
                "description": "Optional timeout override in seconds.",
            },
        },
        "required": ["command"],
    }
    repeatable = True

    @staticmethod
    def _run_non_pty(command: str, cwd: str | None, timeout_seconds: int) -> dict[str, Any]:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "status": "ok" if result.returncode == 0 else "error",
                "exit_code": result.returncode,
                "stdout": _truncate_output(result.stdout),
                "stderr": _truncate_output(result.stderr),
                "used_pty": False,
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "status": "error",
                "error": f"Command timed out after {timeout_seconds}s",
                "stdout": _truncate_output(_decode_timeout_stream(exc.stdout)),
                "stderr": _truncate_output(_decode_timeout_stream(exc.stderr)),
                "used_pty": False,
            }

    @staticmethod
    def _run_with_pty(command: str, cwd: str | None, timeout_seconds: int) -> dict[str, Any]:
        master_fd: int | None = None
        slave_fd: int | None = None
        process: subprocess.Popen[bytes] | None = None
        chunks: list[bytes] = []
        timed_out = False

        try:
            master_fd, slave_fd = pty.openpty()
            # Set environment variables required by TTY-aware CLIs
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"  # Default terminal type for interactive CLI tools
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                env=env,
            )
            os.close(slave_fd)
            slave_fd = None
            _set_pty_size(master_fd)  # Configure PTY window size for terminal detection

            deadline = time.monotonic() + timeout_seconds
            while True:
                now = time.monotonic()
                if now >= deadline:
                    timed_out = True
                    process.kill()
                    break

                if process.poll() is not None:
                    break

                wait_for = min(0.2, max(0.0, deadline - now))
                readable, _, _ = select.select([master_fd], [], [], wait_for)
                if not readable:
                    continue

                try:
                    chunk = os.read(master_fd, 4096)
                except OSError as exc:
                    if exc.errno in (errno.EIO, errno.EBADF):
                        break
                    raise
                if not chunk:
                    break
                chunks.append(chunk)

            if process.poll() is None:
                process.wait(timeout=1)

            while True:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError as exc:
                    if exc.errno in (errno.EIO, errno.EBADF):
                        break
                    raise
                if not chunk:
                    break
                chunks.append(chunk)

            output = _truncate_output(b"".join(chunks).decode("utf-8", errors="replace"))
            if timed_out:
                return {
                    "status": "error",
                    "error": f"Command timed out after {timeout_seconds}s",
                    "stdout": output,
                    "stderr": "",
                    "used_pty": True,
                }

            exit_code = process.returncode if process.returncode is not None else -1
            return {
                "status": "ok" if exit_code == 0 else "error",
                "exit_code": exit_code,
                "stdout": output,
                "stderr": "",
                "used_pty": True,
            }
        finally:
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass

    def execute(self, **kwargs: Any) -> str:
        """Execute a shell command.

        Args:
            **kwargs: Must include command. Optional run_dir used as cwd.

        Returns:
            JSON string with stdout, stderr, and exit_code.
        """
        command = kwargs["command"]
        cwd = kwargs.get("run_dir")
        forced_pty = _should_force_pty_for_command(command)
        use_pty = forced_pty or bool(kwargs.get("pty", False))
        default_timeout = _INTERACTIVE_LOGIN_TIMEOUT if forced_pty else _DEFAULT_TIMEOUT
        timeout_seconds = _parse_timeout_seconds(kwargs.get("timeout_seconds"), default_timeout)

        try:
            payload = (
                self._run_with_pty(command, cwd, timeout_seconds)
                if use_pty
                else self._run_non_pty(command, cwd, timeout_seconds)
            )
            return json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({
                "status": "error",
                "error": str(exc),
            }, ensure_ascii=False)
