"""Compatibility alias tool definitions for Hermes runtime plugins."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-invocation artifact directory context
# ---------------------------------------------------------------------------
# Set this before launching an agent to redirect all write_file calls with
# relative or out-of-tree paths into the run's artifact directory.
# Usage:
#   token = set_artifact_dir(run_dir / "artifacts")
#   try:
#       agent.run_conversation(...)
#   finally:
#       reset_artifact_dir(token)
# ---------------------------------------------------------------------------

_artifact_dir_var: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "artifact_dir", default=None
)


def set_artifact_dir(path: Path) -> contextvars.Token:
    """Set the artifact directory for the current async/thread context."""
    return _artifact_dir_var.set(path)


def reset_artifact_dir(token: contextvars.Token) -> None:
    """Reset the artifact directory context variable."""
    _artifact_dir_var.reset(token)


def _resolve_write_path(requested: str) -> Path:
    """Redirect bare filenames and relative paths to the artifact directory.

    If no artifact directory is set, or if the requested path is already
    absolute and sits inside the artifact directory, return it unchanged.
    """
    artifact_dir = _artifact_dir_var.get()
    p = Path(requested)
    if artifact_dir is None:
        return p
    # Already absolute and inside artifact_dir → allow through
    if p.is_absolute():
        try:
            p.resolve().relative_to(artifact_dir.resolve())
            return p
        except ValueError:
            pass
        # Absolute but outside — redirect using only the filename
        logger.warning(
            "write_file: redirecting out-of-tree path %s → %s",
            requested,
            artifact_dir / p.name,
        )
        return artifact_dir / p.name
    # Relative path → anchor to artifact_dir
    redirected = artifact_dir / p
    logger.debug("write_file: anchoring relative path %s → %s", requested, redirected)
    return redirected

_AGENT_ROOT = Path(__file__).resolve().parents[2]
_HERMES_ROOT = _AGENT_ROOT.parent / "hermes-agent"

if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))
if _HERMES_ROOT.exists() and str(_HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(_HERMES_ROOT))


def _load_skill(args: dict, **_) -> str:
    try:
        from src.core.skills import SkillsLoader

        content = SkillsLoader().get_content(args.get("name", ""))
        return json.dumps(
            {
                "status": "ok" if not content.startswith("Error:") else "error",
                "content": content,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _read_url(args: dict, **_) -> str:
    try:
        from src.tools.web_reader_tool import read_url as _legacy_read_url

        return _legacy_read_url(args.get("url", ""))
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _write_file(args: dict, **_) -> str:
    """Write a file, enforcing artifact_dir for relative / out-of-tree paths."""
    try:
        path = _resolve_write_path(args.get("path", ""))
        content = args.get("content", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return json.dumps({"status": "ok", "path": str(path)}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _bash(args: dict, **_) -> str:
    try:
        from src.tools.bash_tool import BashTool

        # Use the per-invocation artifact_dir as cwd so that agent-generated
        # scripts that write relative paths (e.g. pandas to_csv) land inside
        # the run's artifact directory instead of the process cwd.
        run_dir = args.get("run_dir") or _artifact_dir_var.get()
        tool = BashTool()
        return tool.execute(
            command=args.get("command", ""),
            run_dir=run_dir,
        )
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _edit_file(args: dict, **_) -> str:
    try:
        from src.tools.edit_file_tool import EditFileTool

        tool = EditFileTool()
        return tool.execute(
            path=args.get("path", ""),
            old_text=args.get("old_text", ""),
            new_text=args.get("new_text", ""),
            run_dir=args.get("run_dir"),
        )
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _subagent(args: dict, **kw) -> str:
    try:
        from tools.delegate_tool import delegate_task

        return delegate_task(
            goal=args.get("prompt"),
            context=args.get("description"),
            parent_agent=kw.get("parent_agent"),
        )
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _background_run(args: dict, **_) -> str:
    try:
        from src.tools.background_tools import get_background_manager

        return get_background_manager().run(args.get("command", ""))
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _check_background(args: dict, **_) -> str:
    try:
        from src.tools.background_tools import get_background_manager

        return get_background_manager().check(args.get("task_id"))
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _task_create(args: dict, **_) -> str:
    try:
        from src.tools.task_tools import TASKS

        return TASKS.create(args.get("subject", ""), args.get("description", ""))
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _task_update(args: dict, **_) -> str:
    try:
        from src.tools.task_tools import TASKS

        return TASKS.update(
            args.get("task_id"),
            args.get("status"),
            args.get("addBlockedBy"),
            args.get("addBlocks"),
        )
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _task_list(args: dict, **_) -> str:
    try:
        from src.tools.task_tools import TASKS

        return TASKS.list_all()
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _task_get(args: dict, **_) -> str:
    try:
        from src.tools.task_tools import TASKS

        return TASKS.get(args.get("task_id"))
    except Exception as exc:
        return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)


def _compact(args: dict, **_) -> str:
    return json.dumps({"status": "ok", "message": "Compression triggered"}, ensure_ascii=False)


_SCHEMAS = [
    {
        "name": "write_file",
        "description": "Write text content to a file. Paths are automatically anchored to the current run's artifact directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (relative paths are anchored to the artifact directory)"},
                "content": {"type": "string", "description": "Text content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "load_skill",
        "description": "Load full documentation for a named Vibe-Trading skill.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "read_url",
        "description": "Fetch a web page as markdown text.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Web page URL"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "bash",
        "description": "Execute a shell command in the working directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "run_dir": {"type": "string", "description": "Optional working directory"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "edit_file",
        "description": "Find and replace the first occurrence of old_text with new_text in a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "run_dir": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "subagent",
        "description": "Spawn a subagent with fresh context and return only a summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "background_run",
        "description": "Run a command in the background and return a task id.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "check_background",
        "description": "Check background task status. Omit task_id to list all.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "task_create",
        "description": "Create a new task.",
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["subject"],
        },
    },
    {
        "name": "task_update",
        "description": "Update a task status or dependency links.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "status": {"type": "string"},
                "addBlockedBy": {"type": "array", "items": {"type": "integer"}},
                "addBlocks": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "task_list",
        "description": "List all tasks with status summary.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "task_get",
        "description": "Get full details of a task by id.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "compact",
        "description": "Compress conversation history to free context space.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

_HANDLERS = {
    "write_file": _write_file,
    "load_skill": _load_skill,
    "read_url": _read_url,
    "bash": _bash,
    "edit_file": _edit_file,
    "subagent": _subagent,
    "background_run": _background_run,
    "check_background": _check_background,
    "task_create": _task_create,
    "task_update": _task_update,
    "task_list": _task_list,
    "task_get": _task_get,
    "compact": _compact,
}

TOOLSET_NAME = "compat"

TOOL_REGISTRATIONS = [
    {
        "name": schema["name"],
        "toolset": TOOLSET_NAME,
        "schema": schema,
        "handler": _HANDLERS[schema["name"]],
        "emoji": "↩️",
        "description": schema["description"],
    }
    for schema in _SCHEMAS
]
