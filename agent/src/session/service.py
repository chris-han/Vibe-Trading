"""Session lifecycle orchestration for message flow, attempt creation, and execution scheduling.

V5: Uses AgentLoop instead of the fixed pipeline behind the generate skill.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import json
import logging
import os
import re
import shutil
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from pathlib import Path

from hermes_constants import reset_active_hermes_home, set_active_hermes_home
from src.ui_services import build_backtest_report, expand_artifact_markdown
from src.runtime_prompt_policy import (
    BACKTEST_WORKFLOW_PROMPT,
    OUTPUT_FORMAT_PROMPT,
    DOCUMENT_WORKFLOW_PROMPT,
    MARKET_DATA_WORKFLOW_PROMPT,
    build_session_runtime_prompt,
    load_output_format_skill,
)

logger = logging.getLogger(__name__)

_INCOMPLETE_RESPONSE_PATTERNS = (
    re.compile(r"(?:^|\n)\s*(?:now let me|let me|first(?:,|\s)|first step|starting by).*(?:[:：])\s*$", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*(?:现在让我|让我|首先|先|第一步).*(?:[:：])\s*$"),
)
_INCOMPLETE_CONTINUATION_PATTERNS = (
    re.compile(
        r"^\s*(?:now let me|let me|starting by)\s+(?:set up|create|check|load|run|compare|analy[sz]e|inspect|debug|prepare|build|generate|review|look at|verify|summari[sz]e)\b.*(?:[.!?])?\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*(?:现在让我|让我)\s*(?:设置|创建|检查|加载|运行|比较|分析|查看|调试|准备|构建|生成|验证|总结).*(?:[。！？])?\s*$"),
)
_INCOMPLETE_RESPONSE_KEYWORDS = (
    "let me",
    "now let me",
    "first",
    "first step",
    "starting by",
    "现在让我",
    "让我",
    "首先",
    "第一步",
    "初始化",
)

_INCOMPLETE_RESPONSE_RETRY_PROMPT = (
    "Your previous response stopped before completing the requested action. "
    "Continue from the next concrete step now. Do not restate prior progress, "
    "and do not end with a planning sentence such as 'let me ...'."
)

_FILE_MUTATION_TOOL_NAMES = {
    "write_file",
    "edit_file",
    "replace_in_file",
    "append_file",
    "delete_file",
    "mkdir",
}

_SKILLS_INSTALL_RE = re.compile(r"\bskills\s+(add|install)\b", re.IGNORECASE)
_SKILLS_GLOBAL_FLAG_RE = re.compile(r"(^|\s)--global(\s|$)|(^|\s)-[a-z]*g[a-z]*(\s|$)", re.IGNORECASE)
_TERMINAL_GUARD_PATCH_ATTR = "_semantier_global_skills_guard_patched"
# Captures: simple name, category/name, or https URLs (non-greedy word boundary before space/option)
_SKILL_NAME_RE = re.compile(
    r"(?:add|install)\s+(?:--[a-z-]+\s+)*([a-z0-9][a-z0-9._/-]*|https?://[^\s]+?)(?:\s|$)",
    re.IGNORECASE,
)
_A2UI_FENCE_RE = re.compile(
    r"```a2ui\s*(\{[\s\S]*?\})\s*```",
    re.IGNORECASE,
)


def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())

_DEFAULT_ENABLED_TOOLSETS = [
    "terminal",
    "file",
    "browser",
    "skills",
    "todo",
    "memory",
    "session_search",
    "delegation",
    "cronjob",
    "research",
    "vibe_trading",
]


def _resolve_enabled_toolsets(prompt: str) -> list[str]:
    _ = prompt
    return list(_DEFAULT_ENABLED_TOOLSETS)


def _is_terminal_skills_install_command(command: str) -> bool:
    """Return True when command shells out to external skills install flows."""
    if not isinstance(command, str):
        return False
    normalized = " ".join(command.strip().split())
    if not normalized:
        return False
    return _SKILLS_INSTALL_RE.search(normalized) is not None


def _has_forbidden_global_skills_flags(command: str) -> bool:
    """Return True when command attempts explicit global skills installation."""
    if not _is_terminal_skills_install_command(command):
        return False
    return _SKILLS_GLOBAL_FLAG_RE.search(" ".join(command.strip().split())) is not None


def _extract_skill_name_from_command(command: str) -> Optional[str]:
    """Extract the skill name/identifier from a terminal skills install command.
    
    Returns the name (e.g., 'my-skill') or URL if present, None otherwise.
    """
    normalized = " ".join(command.strip().split())
    match = _SKILL_NAME_RE.search(normalized)
    return match.group(1) if match else None


def _find_skill_in_hermes_home(skill_name: str, hermes_home: Optional[Path]) -> Optional[Path]:
    """Check if a skill exists in the workspace HERMES_HOME/skills directory.
    
    Searches by directory name and respects the tool override hierarchy
    (workspace > external > bundled). Returns the skill directory path if found.
    
    Args:
        skill_name: Name to search for (e.g., 'my-skill', 'productivity/my-skill')
        hermes_home: Workspace HERMES_HOME path
    
    Returns:
        Path to skill directory if found, None otherwise.
    """
    if hermes_home is None:
        return None
    
    skills_dir = hermes_home / "skills"
    if not skills_dir.exists():
        return None
    
    # Extract base name (e.g., 'my-skill' from 'productivity/my-skill')
    base_name = skill_name.rsplit("/", 1)[-1] if "/" in skill_name else skill_name
    base_name = base_name.strip().lower()
    
    if not base_name:
        return None
    
    # Search local skills directory recursively
    try:
        for skill_md in skills_dir.rglob("SKILL.md"):
            if skill_md.parent.name.lower() == base_name:
                return skill_md.parent
    except (OSError, PermissionError):
        pass
    
    return None


def _blocked_global_skills_install_message(
    active_hermes_home: Optional[Path],
    skill_name: Optional[str] = None,
    existing_skill_path: Optional[Path] = None,
) -> str:
    """Build deterministic error text for blocked terminal skill installs.
    
    Checks if the skill already exists in the workspace and provides
    appropriate messaging based on the tool override hierarchy.
    
    Args:
        active_hermes_home: Active workspace HERMES_HOME
        skill_name: Extracted skill name from the command
        existing_skill_path: Path to existing skill if found
    
    Returns:
        Error message for terminal blocking.
    """
    configured = (os.getenv("HERMES_HOME") or "").strip()
    if configured:
        target_dir = f"{configured.rstrip('/')}/skills"
    elif active_hermes_home is not None:
        target_dir = f"{str(active_hermes_home).rstrip('/')}/skills"
    else:
        target_dir = "HERMES_HOME/skills"
    
    # If skill exists, provide location-aware message
    if existing_skill_path is not None:
        relative_path = existing_skill_path.relative_to(
            active_hermes_home / "skills" if active_hermes_home else existing_skill_path
        ) if active_hermes_home else existing_skill_path
        return (
            f"Skill '{skill_name or 'requested'}' is already installed at workspace location: "
            f"skills/{relative_path}.\n"
            "Terminal-driven skills installation is disabled in this runtime. "
            f"To reinstall, use the API endpoint with force=true, or remove and reinstall via the skills toolchain."
        )
    
    return (
        "Blocked: terminal-driven skills installation is disabled in this runtime. "
        "In this runtime, any user request for a global/admin-home skill install resolves to the active HERMES_HOME/skills directory. "
        "Do not run skills add/install via terminal, with or without --global/-g. "
        f"Use the skills toolchain and target: {target_dir}."
    )


def _is_prohibited_skills_path(command: str) -> bool:
    """Check if command targets prohibited skills paths.
    
    Prohibited paths:
    - ~/.agents/skills (legacy path not supported in this runtime)
    - .agents/skills (relative variant)
    
    Returns True if a prohibited path is detected in the command.
    """
    normalized = command.lower()
    return ".agents/skills" in normalized or "~/.agents/skills" in normalized


def _find_skill_in_upstream_scope(skill_name: str) -> Optional[Path]:
    """Check if a skill exists in bundled or external skills directories.
    
    Upstream scope = bundled skills + configured external skills directories.
    These take precedence over local workspace skills.
    
    Args:
        skill_name: Name to search for (e.g., 'my-skill', 'productivity/my-skill')
    
    Returns:
        Path to skill directory if found in upstream, None otherwise.
    """
    try:
        from agent.skill_utils import get_external_skills_dirs
    except ImportError:
        return None
    
    base_name = skill_name.rsplit("/", 1)[-1] if "/" in skill_name else skill_name
    base_name = base_name.strip().lower()
    
    if not base_name:
        return None
    
    # Check external skills directories first
    try:
        for ext_dir in get_external_skills_dirs():
            if ext_dir.exists():
                for skill_md in ext_dir.rglob("SKILL.md"):
                    if skill_md.parent.name.lower() == base_name:
                        return skill_md.parent
    except (OSError, PermissionError):
        pass
    
    return None


def _install_wrapper_terminal_policy_patch(active_hermes_home: Optional[Path]) -> None:
    """Patch terminal adapter to enforce skill installation hierarchy.
    
    Checks for skills in upstream scope (bundled/external). If a skill exists
    upstream, local installation is blocked to respect the override hierarchy:
    - Bundled skills (cannot override)
    - External skills (cannot override)
    - Workspace local skills (can be installed if not in upstream)
    
    Checks for existing skills and provides appropriate messaging based on
    the tool override hierarchy.
    """
    try:
        from tools import terminal_tool as terminal_tool_module
    except Exception:
        return

    if getattr(terminal_tool_module, _TERMINAL_GUARD_PATCH_ATTR, False):
        return

    original_terminal_tool = terminal_tool_module.terminal_tool

    def _resolve_terminal_task_cwd(task_id: Optional[str]) -> Path:
        """Resolve task-scoped cwd from terminal overrides or env fallback."""
        if task_id:
            try:
                overrides_map = getattr(terminal_tool_module, "_task_env_overrides", {})
                task_overrides = overrides_map.get(task_id, {}) if isinstance(overrides_map, dict) else {}
                override_cwd = str(task_overrides.get("cwd") or "").strip()
                if override_cwd:
                    return Path(os.path.expanduser(override_cwd)).resolve()
            except Exception:
                pass

        env_cwd = str(os.getenv("TERMINAL_CWD", "")).strip()
        if env_cwd:
            return Path(os.path.expanduser(env_cwd)).resolve()
        return Path.cwd().resolve()

    def _guarded_terminal_tool(command: str, *args: Any, **kwargs: Any) -> str:
        if _is_terminal_skills_install_command(command):
            # Check for prohibited skills paths first
            if _is_prohibited_skills_path(command):
                error_msg = (
                    "Installation to ~/.agents/skills or .agents/skills is not supported in this runtime. "
                    "Install skills to the active HERMES_HOME/skills directory instead. "
                    "For custom skill locations, configure external_dirs in ~/.hermes/config.yaml."
                )
                return json.dumps(
                    {
                        "output": "",
                        "exit_code": -1,
                        "error": error_msg,
                        "status": "blocked",
                    },
                    ensure_ascii=False,
                )
            
            # Extract skill name and check upstream scope
            skill_name = _extract_skill_name_from_command(command)
            upstream_skill = None
            if skill_name:
                upstream_skill = _find_skill_in_upstream_scope(skill_name)
            
            # If skill exists in upstream, block local installation
            if upstream_skill is not None:
                error_msg = (
                    f"Skill '{skill_name or 'requested'}' already exists in upstream scope "
                    f"(bundled or external skills). Upstream skills override local installations. "
                    f"To use a different version, configure external_dirs in ~/.hermes/config.yaml "
                    f"to change the skill lookup order."
                )
                return json.dumps(
                    {
                        "output": "",
                        "exit_code": -1,
                        "error": error_msg,
                        "status": "blocked",
                    },
                    ensure_ascii=False,
                )
            
            # Check local workspace scope
            existing_skill = None
            if skill_name:
                existing_skill = _find_skill_in_hermes_home(skill_name, active_hermes_home)
            
            error_msg = _blocked_global_skills_install_message(
                active_hermes_home,
                skill_name=skill_name,
                existing_skill_path=existing_skill,
            )
            return json.dumps(
                {
                    "output": "",
                    "exit_code": -1,
                    "error": error_msg,
                    "status": "blocked",
                },
                ensure_ascii=False,
            )
        rewritten_command = command
        materialized_paths: list[str] = []
        task_id_raw = kwargs.get("task_id")
        task_id = str(task_id_raw).strip() if task_id_raw is not None else None
        task_cwd = _resolve_terminal_task_cwd(task_id)

        try:
            rewritten_command, materialized_paths = materialize_shared_skill_scripts_for_command(
                command,
                task_cwd=task_cwd,
            )
        except Exception as exc:
            return json.dumps(
                {
                    "output": "",
                    "exit_code": -1,
                    "error": (
                        "Blocked: failed to materialize shared skill script(s) into the task sandbox. "
                        f"{exc}"
                    ),
                    "status": "blocked",
                },
                ensure_ascii=False,
            )

        if materialized_paths:
            logger.info(
                "Materialized shared skill scripts for task %s into %s: %s",
                task_id or "default",
                task_cwd,
                ", ".join(materialized_paths),
            )

        return original_terminal_tool(rewritten_command, *args, **kwargs)

    terminal_tool_module.terminal_tool = _guarded_terminal_tool
    setattr(terminal_tool_module, _TERMINAL_GUARD_PATCH_ATTR, True)


_FILE_TOOLS_GUARD_PATCH_ATTR = "_semantier_file_tools_skills_guard_patched"


def _install_wrapper_file_policy_patch(active_hermes_home: Optional[Path]) -> None:
    """Patch file_tools write/patch adapters to block writes to .agents/skills paths.

    The upstream hermes-agent runtime does not enforce this boundary, so the
    wrapper applies it here.  Any write_file or patch call whose target path
    contains '.agents/skills' is rejected with a message that directs the
    agent to the workspace-specific HERMES_HOME/skills directory and its
    accompanying config.yaml.
    """
    try:
        from tools import file_tools as file_tools_module
    except Exception:
        return

    if getattr(file_tools_module, _FILE_TOOLS_GUARD_PATCH_ATTR, False):
        return

    config_yaml_hint = (
        f"{active_hermes_home}/config.yaml" if active_hermes_home else "HERMES_HOME/config.yaml"
    )
    skills_dir_hint = (
        f"{active_hermes_home}/skills" if active_hermes_home else "HERMES_HOME/skills"
    )

    def _blocked_file_write_response(filepath: str) -> str:
        return json.dumps(
            {
                "error": (
                    f"Writing to .agents/skills is not supported in this runtime: {filepath}\n"
                    f"Install skills to {skills_dir_hint} instead. "
                    f"For custom skill locations, configure external_dirs in {config_yaml_hint}."
                ),
                "status": "blocked",
            },
            ensure_ascii=False,
        )

    def _targets_prohibited_skills_path(filepath: str) -> bool:
        try:
            normalized = os.path.normpath(os.path.expanduser(filepath))
            resolved = os.path.realpath(os.path.expanduser(filepath))
        except (OSError, ValueError):
            normalized = filepath
            resolved = filepath
        return ".agents/skills" in normalized or ".agents/skills" in resolved

    original_write_file = file_tools_module.write_file_tool
    original_patch = file_tools_module.patch_tool

    def _guarded_write_file(path: str, content: str, *args: Any, **kwargs: Any) -> str:
        if _targets_prohibited_skills_path(path):
            return _blocked_file_write_response(path)
        return original_write_file(path, content, *args, **kwargs)

    def _guarded_patch(mode: str = "replace", path: str = None, *args: Any, **kwargs: Any) -> str:
        if path and _targets_prohibited_skills_path(path):
            return _blocked_file_write_response(path)
        # For V4A patch mode, extract target paths from the patch string
        patch_str = kwargs.get("patch") or (args[3] if len(args) > 3 else None)
        if mode == "patch" and patch_str:
            import re as _re
            for _m in _re.finditer(
                r'^\*\*\*\s+(?:Update|Add|Delete)\s+File:\s*(.+)$', patch_str, _re.MULTILINE
            ):
                if _targets_prohibited_skills_path(_m.group(1).strip()):
                    return _blocked_file_write_response(_m.group(1).strip())
        return original_patch(mode, path, *args, **kwargs)

    file_tools_module.write_file_tool = _guarded_write_file
    file_tools_module.patch_tool = _guarded_patch
    setattr(file_tools_module, _FILE_TOOLS_GUARD_PATCH_ATTR, True)


# Dedicated thread pool limited to four concurrent agents to avoid exhausting the default executor.
_AGENT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent")

_BACKTEST_WORKFLOW_PROMPT = BACKTEST_WORKFLOW_PROMPT
_DOCUMENT_WORKFLOW_PROMPT = DOCUMENT_WORKFLOW_PROMPT
_MARKET_DATA_WORKFLOW_PROMPT = MARKET_DATA_WORKFLOW_PROMPT
_OUTPUT_FORMAT_PROMPT = OUTPUT_FORMAT_PROMPT
_load_output_format_skill = load_output_format_skill


from runtime_env import (
    ensure_runtime_env,
    get_hermes_agent_kwargs,
    get_hermes_home,
    prepare_hermes_project_context,
)
from src.backtest.bootstrap import bootstrap_run_from_prompt, is_backtest_prompt
from src.skills.script_loader import materialize_shared_skill_scripts_for_command
from src.session.events import EventBus
from src.session.models import (
    Attempt,
    AttemptStatus,
    Message,
    Session,
    SessionEvent,
    SessionEventType,
    SessionStatus,
)
from src.session.store import SessionStore


class SessionService:
    """Session lifecycle service.

    Attributes:
        store: Session persistence store.
        event_bus: SSE event bus.
        runs_dir: Root runs directory.
    """

    def __init__(
        self,
        store: SessionStore,
        event_bus: EventBus,
        runs_dir: Path,
        swarm_dir: Optional[Path] = None,
        hermes_home: Optional[Path] = None,
        message_projection_hook: Optional[Callable[[Session, Message], None]] = None,
    ) -> None:
        """Initialize the session service.

        Args:
            store: Session persistence store.
            event_bus: SSE event bus.
            runs_dir: Root runs directory.
            swarm_dir: Workspace-scoped swarm directory (swarm runs written here).
            hermes_home: Workspace-scoped Hermes home used for request-local skill/config discovery.
        """
        self.store = store
        self.event_bus = event_bus
        self.runs_dir = runs_dir
        self.swarm_dir = swarm_dir
        self.hermes_home = hermes_home.resolve() if hermes_home is not None else None
        self.message_projection_hook = message_projection_hook
        self._active_loops: Dict[str, "AgentLoop"] = {}

    @staticmethod
    def _resolve_sandbox_role(session: Optional[Session]) -> str:
        """Return normalized sandbox role for the active session."""
        cfg = session.config if isinstance(getattr(session, "config", None), dict) else {}
        role = str(cfg.get("sandbox_role") or "").strip().lower()
        if role in {"admin", "administrator"}:
            return "administrator"
        return "regular_user"

    def _persist_message(self, session: Session, message: Message) -> None:
        self.store.append_message(message)
        if self.message_projection_hook is None:
            return
        try:
            self.message_projection_hook(session, message)
        except Exception:
            logger.warning(
                "Failed to project message %s for session %s",
                message.message_id,
                session.session_id,
                exc_info=True,
            )

    def create_session(self, title: str = "", config: Optional[Dict[str, Any]] = None) -> Session:
        """Create a new session.

        Args:
            title: Session title.
            config: Session configuration.

        Returns:
            The newly created Session.
        """
        next_config = dict(config or {})
        next_config.setdefault("channel", "web")
        session = Session(title=title, config=next_config)
        self.store.create_session(session)
        self.event_bus.emit(session.session_id, "session.created", {"session_id": session.session_id, "title": title})
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Return a session by ID."""
        return self.store.get_session(session_id)

    def list_sessions(self, limit: int = 50) -> list[Session]:
        """List all sessions."""
        return self.store.list_sessions(limit)

    def _collect_swarm_run_dirs(self, session_id: str) -> list[Path]:
        """Return swarm run directories produced by run_swarm calls in this session."""
        if self.swarm_dir is None:
            return []
        swarm_runs_dir = self.swarm_dir / "runs"
        run_dirs: list[Path] = []
        try:
            for event in self.store.get_events(session_id):
                swarm_run_id = (event.metadata or {}).get("swarm_run_id")
                if not swarm_run_id:
                    continue
                rd = swarm_runs_dir / str(swarm_run_id)
                if rd.exists() and rd.is_dir():
                    run_dirs.append(rd)
        except Exception:
            pass
        return run_dirs

    def _collect_run_dirs(self, session_id: str) -> list[Path]:
        """Collect legacy run_dir paths stored outside the session directory.

        New runs are created under the session folder and are cleaned up
        automatically when the session tree is removed.  This method is kept
        for backward compatibility with older flat-structure runs whose paths
        are stored as absolute paths pointing outside the session directory.
        """
        session_dir = self.store.base_dir / session_id
        run_dirs: list[Path] = []
        try:
            attempts = self.store.list_attempts(session_id)
            for attempt in attempts:
                if attempt.run_dir:
                    p = Path(attempt.run_dir)
                    if not p.exists() or not p.is_dir():
                        continue
                    # Skip dirs already inside the session tree (handled by rmtree)
                    try:
                        p.resolve().relative_to(session_dir.resolve())
                        continue
                    except ValueError:
                        pass
                    run_dirs.append(p)
        except Exception:
            pass
        return run_dirs

    def _collect_registered_artifact_paths(self, session_id: str) -> list[Path]:
        """Collect extra artifact paths explicitly registered for this session."""
        paths: list[Path] = []
        try:
            for item in self.store.list_artifacts(session_id):
                raw = str((item or {}).get("path") or "").strip()
                if raw:
                    paths.append(Path(raw))
        except Exception:
            pass
        return paths

    @staticmethod
    def _remove_artifact_path(path: Path) -> None:
        """Best-effort deletion for a tracked artifact path."""
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            return
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    def _collect_session_owned_run_dirs(self, session_id: str) -> list[Path]:
        """Collect run directories tagged to a session via req.json context.

        Some attempts may switch to a different final run_dir (for example,
        when delegating to a tool-created backtest directory). In those cases,
        the initially created run directory can be left behind. We treat any
        run under runs_dir with req.json context.session_id == session_id as
        owned by that session and delete it during cascade cleanup.
        """
        run_dirs: list[Path] = []
        if not self.runs_dir.exists() or not self.runs_dir.is_dir():
            return run_dirs

        for candidate in self.runs_dir.iterdir():
            if not candidate.is_dir():
                continue
            req_file = candidate / "req.json"
            if not req_file.exists() or not req_file.is_file():
                continue
            try:
                payload = json.loads(req_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            context = payload.get("context") if isinstance(payload, dict) else None
            tagged_session_id = context.get("session_id") if isinstance(context, dict) else None
            if str(tagged_session_id or "").strip() == session_id:
                run_dirs.append(candidate)

        return run_dirs

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all deterministic artifact directories.

        This removes the session tree itself, which includes session-scoped
        uploads, and also removes linked backtest run directories plus linked
        swarm run directories that live outside the session folder.
        """
        legacy_run_dirs = self._collect_run_dirs(session_id)
        session_owned_run_dirs = self._collect_session_owned_run_dirs(session_id)
        registered_artifacts = self._collect_registered_artifact_paths(session_id)
        swarm_run_dirs = self._collect_swarm_run_dirs(session_id)
        self.event_bus.clear(session_id)
        ok = self.store.delete_session(session_id)
        for rd in {*(legacy_run_dirs), *(session_owned_run_dirs), *(swarm_run_dirs), *(registered_artifacts)}:
            self._remove_artifact_path(rd)
        return ok

    def delete_sessions(self, session_ids: list[str]) -> Dict[str, Any]:
        """Delete multiple sessions and their linked artifact directories."""
        deleted: list[str] = []
        missing: list[str] = []
        for session_id in session_ids:
            legacy_run_dirs = self._collect_run_dirs(session_id)
            session_owned_run_dirs = self._collect_session_owned_run_dirs(session_id)
            registered_artifacts = self._collect_registered_artifact_paths(session_id)
            swarm_run_dirs = self._collect_swarm_run_dirs(session_id)
            self.event_bus.clear(session_id)
            if self.store.delete_session(session_id):
                deleted.append(session_id)
                for rd in {*(legacy_run_dirs), *(session_owned_run_dirs), *(swarm_run_dirs), *(registered_artifacts)}:
                    self._remove_artifact_path(rd)
            else:
                missing.append(session_id)
        return {
            "deleted": deleted,
            "missing": missing,
        }

    def _update_session_state(
        self,
        session_id: str,
        *,
        status: Optional[SessionStatus] = None,
        last_attempt_id: Optional[str] = None,
    ) -> Optional[Session]:
        """Persist the latest session lifecycle state."""
        session = self.store.get_session(session_id)
        if not session:
            return None
        if status is not None:
            session.status = status
        if last_attempt_id is not None:
            session.last_attempt_id = last_attempt_id
        session.updated_at = datetime.now().isoformat()
        self.store.update_session(session)
        return session

    def _record_event(
        self,
        session_id: str,
        event_type: str,
        *,
        attempt_id: Optional[str] = None,
        role: Optional[str] = None,
        content: Optional[str] = None,
        reasoning: Optional[str] = None,
        tool: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        args: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionEvent:
        """Persist a canonical session event."""
        event = SessionEvent(
            session_id=session_id,
            attempt_id=attempt_id,
            event_type=event_type,
            role=role,
            content=content,
            reasoning=reasoning,
            tool=tool,
            tool_call_id=tool_call_id,
            args=args,
            status=status,
            metadata=metadata or {},
        )
        self.store.append_event(event)
        return event

    async def send_message(self, session_id: str, content: str, role: str = "user") -> Dict[str, Any]:
        """Send a message to a session and trigger execution.

        Args:
            session_id: Session ID.
            content: Message content.
            role: Message role.

        Returns:
            Dictionary containing message_id and attempt_id.
        """
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        message = Message(session_id=session_id, role=role, content=content)
        self._persist_message(session, message)
        self.event_bus.emit(session_id, "message.received", {"message_id": message.message_id, "role": role, "content": content})

        if role != "user":
            return {"message_id": message.message_id}

        attempt = Attempt(session_id=session_id, parent_attempt_id=session.last_attempt_id, prompt=content)
        self.store.create_attempt(attempt)
        self._update_session_state(
            session_id,
            status=SessionStatus.RUNNING,
            last_attempt_id=attempt.attempt_id,
        )
        self._record_event(
            session_id,
            SessionEventType.ATTEMPT_CREATED.value,
            attempt_id=attempt.attempt_id,
            metadata={"prompt": content},
        )
        self.event_bus.emit(session_id, "attempt.created", {"attempt_id": attempt.attempt_id, "prompt": content})

        asyncio.create_task(self._run_attempt(session, attempt))
        return {"message_id": message.message_id, "attempt_id": attempt.attempt_id}

    async def resume_attempt(self, session_id: str, attempt_id: str, user_input: str) -> Dict[str, Any]:
        """Resume an attempt that is waiting for user input.

        Args:
            session_id: Session ID.
            attempt_id: Attempt ID.
            user_input: User reply content.

        Returns:
            Dictionary containing status and attempt_id.
        """
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        attempt = self.store.get_attempt(session_id, attempt_id)
        if not attempt:
            raise ValueError(f"Attempt {attempt_id} not found")
        if attempt.status != AttemptStatus.WAITING_USER:
            raise ValueError(f"Attempt {attempt_id} is not waiting for user input")

        message = Message(session_id=session_id, role="user", content=user_input, linked_attempt_id=attempt_id)
        self._persist_message(session, message)

        # Append the user's reply to the prompt and rerun the attempt.
        attempt.prompt = f"{attempt.prompt}\n\nUser reply: {user_input}"
        attempt.status = AttemptStatus.RUNNING
        self.store.update_attempt(attempt)
        self._update_session_state(
            session_id,
            status=SessionStatus.RUNNING,
            last_attempt_id=attempt_id,
        )
        self._record_event(
            session_id,
            SessionEventType.ATTEMPT_STARTED.value,
            attempt_id=attempt_id,
            metadata={"resumed": True},
        )
        self.event_bus.emit(session_id, "attempt.resumed", {"attempt_id": attempt_id, "user_input": user_input})

        asyncio.create_task(self._run_attempt(session, attempt))
        return {"status": "resumed", "attempt_id": attempt_id}

    def get_messages(self, session_id: str, limit: int = 100) -> list[Message]:
        """Return the message history."""
        messages = self.store.get_messages(session_id, limit)
        expanded: list[Message] = []
        attempt_run_dirs: dict[str, Path] = {}

        for msg in messages:
            if msg.role != "assistant" or not msg.content or not msg.linked_attempt_id:
                expanded.append(msg)
                continue

            run_dir = attempt_run_dirs.get(msg.linked_attempt_id)
            if run_dir is None:
                attempt = self.store.get_attempt(session_id, msg.linked_attempt_id)
                if attempt and attempt.run_dir:
                    candidate = Path(attempt.run_dir)
                    if candidate.exists():
                        run_dir = candidate
                        attempt_run_dirs[msg.linked_attempt_id] = candidate

            if run_dir is None:
                expanded.append(msg)
                continue

            content = expand_artifact_markdown(msg.content, run_dir)
            if content == msg.content:
                expanded.append(msg)
                continue

            expanded.append(
                Message(
                    message_id=msg.message_id,
                    session_id=msg.session_id,
                    role=msg.role,
                    content=content,
                    created_at=msg.created_at,
                    linked_attempt_id=msg.linked_attempt_id,
                    metadata=msg.metadata,
                )
            )

        return expanded

    def get_events(self, session_id: str, limit: int = 1000) -> list[SessionEvent]:
        """Return canonical session events."""
        return self.store.get_events(session_id, limit)

    def export_atropos_trajectory(self, session_id: str) -> Dict[str, Any]:
        """Project canonical events into an Atropos/Hermes trajectory entry."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        events = self.store.get_events(session_id, limit=100000)
        conversations: list[Dict[str, str]] = []
        used_tools: set[str] = set()

        def _render_assistant(turn: Optional[Dict[str, Any]]) -> Optional[str]:
            if not turn:
                return None
            parts: list[str] = []
            reasoning = "".join(turn["reasoning"]).strip()
            if reasoning:
                parts.append(f"<think>\n{reasoning}\n</think>")
            tool_calls = turn["tool_calls"]
            if tool_calls:
                for tc in tool_calls:
                    parts.append("<tool_call>\n" + json.dumps(tc, ensure_ascii=False) + "\n</tool_call>")
            text = "".join(turn["text"]).strip()
            if text:
                parts.append(text)
            rendered = "\n".join(parts).strip()
            return rendered or None

        def _flush_assistant(turn: Optional[Dict[str, Any]]) -> None:
            rendered = _render_assistant(turn)
            if rendered:
                conversations.append({"from": "gpt", "value": rendered})

        def _flush_tool_results(results: list[Dict[str, Any]]) -> None:
            if not results:
                return
            payload = "\n".join(
                "<tool_response>\n" + json.dumps(item, ensure_ascii=False) + "\n</tool_response>"
                for item in results
            )
            conversations.append({"from": "tool", "value": payload})

        current_assistant: Optional[Dict[str, Any]] = None
        pending_tool_results: list[Dict[str, Any]] = []

        for event in events:
            if event.event_type == SessionEventType.MESSAGE_CREATED.value:
                if event.role == "user":
                    _flush_assistant(current_assistant)
                    current_assistant = None
                    _flush_tool_results(pending_tool_results)
                    pending_tool_results = []
                    conversations.append({"from": "human", "value": event.content or ""})
                    continue
                if event.role == "assistant":
                    _flush_tool_results(pending_tool_results)
                    pending_tool_results = []
                    if current_assistant is None:
                        current_assistant = {"reasoning": [], "text": [], "tool_calls": []}
                    if event.content and not "".join(current_assistant["text"]).strip():
                        current_assistant["text"].append(event.content)
                    _flush_assistant(current_assistant)
                    current_assistant = None
                    continue

            if event.event_type == SessionEventType.REASONING_DELTA.value:
                _flush_tool_results(pending_tool_results)
                pending_tool_results = []
                if current_assistant is None:
                    current_assistant = {"reasoning": [], "text": [], "tool_calls": []}
                if event.reasoning:
                    current_assistant["reasoning"].append(event.reasoning)
                continue

            if event.event_type == SessionEventType.TEXT_DELTA.value:
                _flush_tool_results(pending_tool_results)
                pending_tool_results = []
                if current_assistant is None:
                    current_assistant = {"reasoning": [], "text": [], "tool_calls": []}
                if event.content:
                    current_assistant["text"].append(event.content)
                continue

            if event.event_type == SessionEventType.TOOL_CALL.value:
                _flush_tool_results(pending_tool_results)
                pending_tool_results = []
                if current_assistant is None:
                    current_assistant = {"reasoning": [], "text": [], "tool_calls": []}
                used_tools.add(str(event.tool or ""))
                current_assistant["tool_calls"].append({
                    "name": event.tool or "",
                    "arguments": event.args or {},
                })
                continue

            if event.event_type == SessionEventType.TOOL_RESULT.value:
                if current_assistant is not None:
                    _flush_assistant(current_assistant)
                    current_assistant = None
                pending_tool_results.append({
                    "tool_call_id": event.tool_call_id or "",
                    "name": event.tool or "",
                    "content": event.content or "",
                    "status": event.status or "ok",
                })
                if event.tool:
                    used_tools.add(event.tool)
                continue

        _flush_assistant(current_assistant)
        _flush_tool_results(pending_tool_results)

        tool_defs = [{"name": name, "description": f"Tool {name}", "parameters": {"type": "object"}} for name in sorted(t for t in used_tools if t)]
        system_value = (
            "You are a function calling AI model. Use reasoning in <think> tags. "
            "Emit tool invocations in <tool_call> blocks and consume results in <tool_response> blocks.\n"
            f"<tools>\n{json.dumps(tool_defs, ensure_ascii=False)}\n</tools>"
        )

        return {
            "session_id": session_id,
            "title": session.title,
            "source_file": str(self.store._events_file(session_id)),
            "trajectory": {
                "conversations": [{"from": "system", "value": system_value}, *conversations],
                "timestamp": session.updated_at,
                "model": os.getenv("HERMES_MODEL", ""),
                "completed": True,
                "metadata": {
                    "session_id": session_id,
                    "event_count": len(events),
                    "tools_used": sorted(t for t in used_tools if t),
                },
            },
        }

    def get_attempts(self, session_id: str) -> list[Attempt]:
        """Return all execution attempts."""
        return self.store.list_attempts(session_id)

    def get_attempt(self, session_id: str, attempt_id: str) -> Optional[Attempt]:
        """Return a single execution attempt."""
        return self.store.get_attempt(session_id, attempt_id)

    def cancel_current(self, session_id: str) -> bool:
        """Cancel the currently running agent for a session.

        Args:
            session_id: Session ID.

        Returns:
            Whether cancellation succeeded. True means an active agent existed and received a cancel signal.
        """
        agent = self._active_loops.get(session_id)
        if agent is None:
            return False
        self._update_session_state(session_id, status=SessionStatus.CANCELLED)
        session = self.store.get_session(session_id)
        if session and session.last_attempt_id:
            attempt = self.store.get_attempt(session_id, session.last_attempt_id)
            if attempt and attempt.status == AttemptStatus.RUNNING:
                attempt.mark_cancelled("cancelled by user")
                self.store.update_attempt(attempt)
        agent.interrupt("cancelled by user")
        return True

    @staticmethod
    def _is_cancelled_error(error: Optional[str]) -> bool:
        """Best-effort detection for user cancellation."""
        text = str(error or "").strip().lower()
        return "cancelled by user" in text or text == "cancelled" or "interrupted" in text

    @staticmethod
    def _looks_incomplete_final_response(text: str) -> bool:
        """Return whether a final assistant response looks truncated or unfinished."""
        normalized = str(text or "").strip()
        if not normalized:
            return False
        lowered = normalized.casefold()
        if normalized.endswith((":", "：")) and any(keyword in lowered for keyword in _INCOMPLETE_RESPONSE_KEYWORDS):
            return True
        if any(pattern.search(normalized) for pattern in _INCOMPLETE_RESPONSE_PATTERNS):
            return True
        if len(normalized) > 240 or "\n" in normalized:
            return False
        trailing_segment = re.split(r"(?<=[.!?。！？])\s+", normalized)[-1].strip()
        return any(
            pattern.search(candidate)
            for candidate in (normalized, trailing_segment)
            for pattern in _INCOMPLETE_CONTINUATION_PATTERNS
        )

    @staticmethod
    def _extract_a2ui_schema_from_text(text: str) -> tuple[str, Optional[Dict[str, Any]]]:
        """Extract one fenced ```a2ui JSON block from assistant text when present."""
        raw_text = str(text or "")
        match = _A2UI_FENCE_RE.search(raw_text)
        if not match:
            return raw_text, None

        json_payload = (match.group(1) or "").strip()
        if not json_payload:
            return raw_text, None

        try:
            parsed = json.loads(json_payload)
        except Exception:
            return raw_text, None

        if not isinstance(parsed, dict):
            return raw_text, None

        if not SessionService._is_valid_a2ui_payload(parsed):
            return raw_text, None

        stripped = (raw_text[: match.start()] + raw_text[match.end() :]).strip()
        return stripped, parsed

    @staticmethod
    def _is_valid_a2ui_payload(payload: Dict[str, Any]) -> bool:
        has_root = isinstance(payload.get("root"), dict)
        has_nodes = isinstance(payload.get("nodes"), list)
        has_blocks = isinstance(payload.get("blocks"), list)
        if not (has_root or has_nodes or has_blocks):
            return False

        if has_root and not SessionService._is_valid_a2ui_root(payload["root"]):
            return False

        if has_nodes and any(not isinstance(node, dict) for node in payload["nodes"]):
            return False

        if has_blocks and any(not isinstance(block, dict) for block in payload["blocks"]):
            return False

        return True

    @staticmethod
    def _is_valid_a2ui_root(root: Dict[str, Any]) -> bool:
        component = root.get("component")
        if not _is_non_empty_text(component):
            return False

        props = root.get("props")
        if props is not None and not isinstance(props, dict):
            return False

        if str(component).strip() == "schema_form":
            if not isinstance(props, dict):
                return False
            return SessionService._is_valid_schema_form_props(props)

        return True

    @staticmethod
    def _is_valid_schema_form_props(props: Dict[str, Any]) -> bool:
        fields = props.get("fields")
        if not isinstance(fields, list) or not fields:
            return False

        for field in fields:
            if not isinstance(field, dict):
                return False

            for key in ("key", "label", "type"):
                if not _is_non_empty_text(field.get(key)):
                    return False

            required = field.get("required")
            if required is not None and not isinstance(required, bool):
                return False

            field_type = str(field.get("type")).strip().lower()
            if field_type == "select":
                options = field.get("options")
                if not isinstance(options, list) or not options:
                    return False
                for option in options:
                    if not isinstance(option, dict):
                        return False
                    if not _is_non_empty_text(option.get("label")):
                        return False
                    if not _is_non_empty_text(option.get("value")):
                        return False

        return True

    async def _run_attempt(self, session: Session, attempt: Attempt) -> None:
        """Execute an Attempt in the background."""
        attempt.mark_running()
        self.store.update_attempt(attempt)
        self._update_session_state(
            session.session_id,
            status=SessionStatus.RUNNING,
            last_attempt_id=attempt.attempt_id,
        )
        self._record_event(
            session.session_id,
            SessionEventType.ATTEMPT_STARTED.value,
            attempt_id=attempt.attempt_id,
        )
        self.event_bus.emit(session.session_id, "attempt.started", {"attempt_id": attempt.attempt_id})

        try:
            messages = self.store.get_messages(session.session_id)
            result = await self._run_with_agent(attempt, messages=messages)
            if result.get("status") == "success":
                attempt.mark_completed(summary=result.get("content", ""))
                next_session_status = SessionStatus.COMPLETED
            elif result.get("status") == "cancelled":
                attempt.mark_cancelled(error=result.get("reason", "cancelled"))
                next_session_status = SessionStatus.CANCELLED
            else:
                attempt.mark_failed(error=result.get("reason", "unknown"))
                next_session_status = SessionStatus.FAILED
            attempt.run_dir = result.get("run_dir")
            attempt.metrics = result.get("metrics")

            self.store.update_attempt(attempt)
            self._update_session_state(
                session.session_id,
                status=next_session_status,
                last_attempt_id=attempt.attempt_id,
            )
            reply_metadata = {}
            has_run_artifact = bool(result.get("has_run_artifact"))
            if attempt.run_dir and has_run_artifact:
                reply_metadata["run_id"] = Path(attempt.run_dir).name
                reply_metadata["has_run_artifact"] = True
            reply_metadata["status"] = attempt.status.value
            if attempt.metrics:
                reply_metadata["metrics"] = attempt.metrics
            ui_schema = result.get("ui_schema")
            if isinstance(ui_schema, dict):
                reply_metadata["ui_schema"] = ui_schema
            retry_message = result.get("retry_message")
            if retry_message:
                reply_metadata["retry_message"] = retry_message

            reply = Message(
                session_id=session.session_id, role="assistant",
                content=self._format_result_message(attempt),
                linked_attempt_id=attempt.attempt_id,
                metadata=reply_metadata,
            )
            self._persist_message(session, reply)
            self.event_bus.emit(
                session.session_id,
                SessionEventType.MESSAGE_CREATED.value,
                {
                    "message_id": reply.message_id,
                    "role": reply.role,
                    "content": reply.content,
                    "created_at": reply.created_at,
                    "linked_attempt_id": reply.linked_attempt_id,
                    "metadata": reply.metadata,
                },
            )
            self._record_event(
                session.session_id,
                SessionEventType.ATTEMPT_COMPLETED.value if attempt.status == AttemptStatus.COMPLETED else SessionEventType.ATTEMPT_FAILED.value,
                attempt_id=attempt.attempt_id,
                status=attempt.status.value,
                metadata={
                    "summary": attempt.summary,
                    "error": attempt.error,
                    "run_dir": attempt.run_dir,
                    "metrics": attempt.metrics,
                },
            )
            self.event_bus.emit(
                session.session_id,
                "attempt.completed" if attempt.status == AttemptStatus.COMPLETED else "attempt.failed",
                {
                    "attempt_id": attempt.attempt_id,
                    "status": attempt.status.value,
                    "summary": attempt.summary,
                    "error": attempt.error,
                    "run_dir": attempt.run_dir,
                    "has_run_artifact": has_run_artifact,
                    "metrics": attempt.metrics,
                    **({"retry_message": retry_message} if retry_message else {}),
                },
            )

        except Exception as exc:
            error_text = str(exc)
            if self._is_cancelled_error(error_text):
                attempt.mark_cancelled(error=error_text)
                next_session_status = SessionStatus.CANCELLED
            else:
                attempt.mark_failed(error=error_text)
                next_session_status = SessionStatus.FAILED
            self.store.update_attempt(attempt)
            self._update_session_state(
                session.session_id,
                status=next_session_status,
                last_attempt_id=attempt.attempt_id,
            )
            self._record_event(
                session.session_id,
                SessionEventType.ATTEMPT_FAILED.value,
                attempt_id=attempt.attempt_id,
                status=attempt.status.value,
                metadata={"error": error_text},
            )
            self.event_bus.emit(
                session.session_id,
                "attempt.failed",
                {"attempt_id": attempt.attempt_id, "status": attempt.status.value, "error": error_text},
            )

    async def _run_with_agent(self, attempt: Attempt, messages: list = None) -> Dict[str, Any]:
        """Execute an attempt using Hermes AIAgent directly.

        Args:
            attempt: Current execution attempt.
            messages: Session message history.

        Returns:
            Result dictionary containing status, run_dir, run_id, metrics, and related fields.
        """
        import os
        import sys
        prepare_hermes_project_context(chdir=True)
        _HERMES = Path(__file__).resolve().parents[3] / "hermes-agent"
        if str(_HERMES) not in sys.path:
            sys.path.insert(0, str(_HERMES))
        import run_agent as _hermes_run_agent
        from run_agent import AIAgent
        from src.core.state import RunStateStore

        sid = attempt.session_id
        attempt_id = attempt.attempt_id
        is_backtest_task = is_backtest_prompt(attempt.prompt)
        hermes_home_token = (
            set_active_hermes_home(self.hermes_home)
            if self.hermes_home is not None
            else None
        )
        _install_wrapper_terminal_policy_patch(self.hermes_home)
        _install_wrapper_file_policy_patch(self.hermes_home)
        latest_prepared_run_dir: str | None = None
        latest_backtest_run_dir: str | None = None
        latest_useful_tool_output: str | None = None
        saw_reportable_tool_run = False
        saw_successful_backtest = False
        saw_successful_file_mutation = False

        state_store = RunStateStore()
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        run_dir = state_store.create_run_dir(self.runs_dir)
        state_store.save_request(run_dir, attempt.prompt, {"session_id": sid})
        self.store.register_artifact(sid, str(run_dir), kind="run_dir")

        if is_backtest_prompt(attempt.prompt):
            try:
                bootstrap_run_from_prompt(run_dir, attempt.prompt)
            except Exception:
                logger.warning("Failed to bootstrap backtest run_dir=%s", run_dir, exc_info=True)

        # Bridge Hermes callbacks -> Vibe-Trading SSE events
        def _on_tool_progress(
            event_type: str,
            tool_name: str = "",
            preview: str = "",
            args: Optional[dict] = None,
            **kwargs,
        ) -> None:
            nonlocal latest_prepared_run_dir, latest_backtest_run_dir, latest_useful_tool_output
            nonlocal saw_successful_backtest, saw_successful_file_mutation
            if event_type == "tool.started":
                if tool_name == "backtest":
                    started_run_dir = str((args or {}).get("run_dir") or "").strip()
                    if started_run_dir:
                        latest_backtest_run_dir = started_run_dir
                self._record_event(
                    sid,
                    SessionEventType.TOOL_CALL.value,
                    attempt_id=attempt_id,
                    tool=tool_name,
                    args=args or {},
                    status="running",
                )
                logger.info("[%s] tool.started  %s  args=%s", sid[:8], tool_name, str(args or {})[:300])
                self.event_bus.emit(sid, "tool_call", {
                    "attempt_id": attempt_id,
                    "tool": tool_name,
                    "args": args or {},
                })
                if tool_name == "run_swarm":
                    preset = str((args or {}).get("preset_name") or "swarm").strip()
                    variables = (args or {}).get("variables") or {}
                    vars_preview = ", ".join(
                        f"{k}={v}" for k, v in variables.items() if str(v).strip()
                    )
                    progress_msg = (
                        f"Running `{preset}`"
                        + (f" for {vars_preview}" if vars_preview else "")
                        + ". This usually takes a few minutes."
                    )
                    self._record_event(
                        sid,
                        SessionEventType.TOOL_PROGRESS.value,
                        attempt_id=attempt_id,
                        tool=tool_name,
                        content=progress_msg,
                    )
                    self.event_bus.emit(sid, "tool_progress", {
                        "attempt_id": attempt_id,
                        "tool": tool_name,
                        "preview": progress_msg,
                    })
            elif event_type == "tool.completed":
                is_error = kwargs.get("is_error", False)
                preview_str = str(preview or "")[:500]
                parsed_result: Dict[str, Any] | None = None
                try:
                    parsed_result = json.loads(str(preview or ""))
                except Exception:
                    parsed_result = None

                if not is_error and parsed_result:
                    if tool_name == "setup_backtest_run":
                        saw_reportable_tool_run = True
                        latest_prepared_run_dir = str(parsed_result.get("run_dir") or "") or latest_prepared_run_dir
                    elif tool_name == "backtest":
                        saw_reportable_tool_run = True
                        resolved = parsed_result.get("resolved_run_dir") or parsed_result.get("run_dir")
                        if parsed_result.get("status") == "ok" and resolved:
                            latest_backtest_run_dir = str(resolved)
                            saw_successful_backtest = True
                    elif tool_name == "run_swarm":
                        saw_reportable_tool_run = True

                if not is_error and tool_name in _FILE_MUTATION_TOOL_NAMES:
                    if tool_name == "delete_file":
                        saw_successful_file_mutation = bool(parsed_result is None or parsed_result.get("success", True))
                    else:
                        saw_successful_file_mutation = True

                if not is_error:
                    useful_tool_output = self._extract_useful_tool_output(tool_name, parsed_result, str(preview or ""))
                    if useful_tool_output:
                        latest_useful_tool_output = useful_tool_output

                if is_error:
                    logger.error("[%s] tool.error    %s  result=%s", sid[:8], tool_name, preview_str)
                else:
                    logger.info("[%s] tool.completed %s  result=%s", sid[:8], tool_name, preview_str[:200])
                tool_result_meta: Dict[str, Any] = {"is_error": is_error}
                if not is_error and tool_name == "run_swarm" and parsed_result:
                    swarm_run_id = parsed_result.get("run_id")
                    if swarm_run_id:
                        tool_result_meta["swarm_run_id"] = str(swarm_run_id)
                self._record_event(
                    sid,
                    SessionEventType.TOOL_RESULT.value,
                    attempt_id=attempt_id,
                    tool=tool_name,
                    content=preview_str,
                    status="error" if is_error else "ok",
                    metadata=tool_result_meta,
                )
                self.event_bus.emit(sid, "tool_result", {
                    "attempt_id": attempt_id,
                    "tool": tool_name,
                    "is_error": is_error,
                    "status": "error" if is_error else "ok",
                    "preview": preview_str,
                })
            elif event_type == "subagent_progress":
                progress_text = str(preview or tool_name or "")[:500]
                logger.info("[%s] tool.progress  %s", sid[:8], progress_text[:200])
                self._record_event(
                    sid,
                    SessionEventType.TOOL_PROGRESS.value,
                    attempt_id=attempt_id,
                    tool=str(kwargs.get("parent_tool") or "delegate_task"),
                    content=progress_text,
                )
                self.event_bus.emit(sid, "tool_progress", {
                    "attempt_id": attempt_id,
                    "tool": str(kwargs.get("parent_tool") or "delegate_task"),
                    "preview": progress_text,
                })

        def _on_delta(chunk: str) -> None:
            if chunk is not None:
                self._record_event(
                    sid,
                    SessionEventType.TEXT_DELTA.value,
                    attempt_id=attempt_id,
                    role="assistant",
                    content=chunk,
                )
            self.event_bus.emit(sid, "text_delta", {
                "attempt_id": attempt_id,
                "content": chunk,
            })

        def _on_reasoning(text: str) -> None:
            if text:
                self._record_event(
                    sid,
                    SessionEventType.REASONING_DELTA.value,
                    attempt_id=attempt_id,
                    role="assistant",
                    reasoning=text,
                )
            self.event_bus.emit(sid, "reasoning_delta", {
                "attempt_id": attempt_id,
                "content": text,
            })

        def _on_tool_generation(tool_name: str) -> None:
            if tool_name == "execute_code":
                logger.error(
                    "[%s] permission_denied execute_code attempted by model; "
                    "toolset is disabled for Vibe-Trading session runtime",
                    sid[:8],
                )

        active_session = self.store.get_session(sid) or Session()
        sandbox_role = self._resolve_sandbox_role(active_session)

        ensure_runtime_env()
        agent_kwargs = get_hermes_agent_kwargs()

        if bool(agent_kwargs.get("save_trajectories")):
            from agent.trajectory import save_trajectory as _save_trajectory_fn

            trajectories_dir = (get_hermes_home() / "trajectories").resolve()
            trajectories_dir.mkdir(parents=True, exist_ok=True)

            def _save_wrapper_trajectory(trajectory, model, completed, filename=None):
                date_suffix = datetime.now().strftime("%Y%m%d")
                if completed:
                    target_name = f"semantier_trajectory_{date_suffix}.jsonl"
                else:
                    target_name = f"semantier_trajectory_failed_{date_suffix}.jsonl"
                target_file = trajectories_dir / target_name
                _save_trajectory_fn(trajectory, model, completed, filename=str(target_file))

            # Force trajectory logs into backend wrapper scope regardless of process cwd.
            _hermes_run_agent._save_trajectory_to_file = _save_wrapper_trajectory

        # Configure terminal/file tool root via env var and per-session task
        # override so every session starts in agent/ rather than the full repo
        # root. This prevents search_files from crawling hermes-agent/ and other
        # top-level sibling directories.
        #
        # TERMINAL_CWD is the global fallback; register_task_env_overrides pins
        # the exact session-scoped cwd in Hermes' tool layer so that file ops
        # and terminal commands resolve relative paths without any absolute path
        # being injected via the prompt. The Vibe-Trading plugin loads through
        # the installed Hermes entry-point package, so cwd is not part of
        # plugin discovery.
        repo_root = prepare_hermes_project_context(chdir=False)
        agent_root = repo_root / "agent"

        # TERMINAL_CWD may be set in .env as a relative path (e.g. a username
        # like 'chris'). Resolve it against agent_root so the tool layer always
        # receives an absolute path.
        _raw_cwd = os.getenv("TERMINAL_CWD", "")
        if _raw_cwd and not os.path.isabs(_raw_cwd):
            file_root = (agent_root / _raw_cwd).resolve()
        elif _raw_cwd:
            file_root = Path(_raw_cwd).resolve()
        else:
            file_root = agent_root
        # Ensure the directory exists so Hermes doesn't reject it.
        file_root.mkdir(parents=True, exist_ok=True)

        try:
            from tools.terminal_tool import register_task_env_overrides
            register_task_env_overrides(sid, {
                "cwd": str(file_root),
                "safe_write_root": str(file_root),
            })
        except Exception:
            pass  # Non-fatal: TERMINAL_CWD env-var fallback still applies

        agent = AIAgent(
            model=os.getenv("HERMES_MODEL", ""),
            max_iterations=50,
            quiet_mode=True,
            session_id=sid,
            enabled_toolsets=_resolve_enabled_toolsets(attempt.prompt),
            disabled_toolsets=["code_execution"],
            tool_progress_callback=_on_tool_progress,
            tool_gen_callback=_on_tool_generation,
            reasoning_callback=_on_reasoning,
            stream_delta_callback=_on_delta,
            ephemeral_system_prompt=build_session_runtime_prompt(
                str(run_dir),
                sid,
                active_session.config.get("channel", ""),
                sandbox_role=sandbox_role,
            ),
            skip_context_files=True,
            **agent_kwargs,
        )
        self._active_loops[sid] = agent

        history = self._convert_messages_to_history(messages) if messages else []

        from src.vibe_trading_helper import reset_session_runs_dir, set_session_runs_dir, set_session_swarm_dir, reset_session_swarm_dir
        _runs_token = set_session_runs_dir(self.runs_dir)
        _swarm_token = set_session_swarm_dir(self.swarm_dir) if self.swarm_dir is not None else None
        # Configure Hermes built-in file/terminal tools to stay inside the active
        # run directory. Use artifacts/ as cwd so relative outputs land there,
        # while still allowing explicit edits to config.json or code/.
        try:
            from tools.terminal_tool import register_task_env_overrides, clear_task_env_overrides
            workspace_root = self.runs_dir.parent.resolve()
            if sandbox_role == "administrator":
                register_task_env_overrides(sid, {
                    "cwd": str(file_root),
                    "safe_read_root": str(file_root),
                    "safe_write_root": str(file_root),
                    "display_cwd": "/workspace/admin",
                    "display_safe_read_root": "/workspace/admin",
                    "display_safe_write_root": "/workspace/admin",
                })
            else:
                register_task_env_overrides(sid, {
                    "cwd": str(run_dir / "artifacts"),
                    "safe_read_root": str(workspace_root),
                    "safe_write_root": str(run_dir),
                    "display_cwd": "/workspace/run/artifacts",
                    "display_safe_read_root": "/workspace",
                    "display_safe_write_root": "/workspace/run",
                })
            _hermes_overrides_set = True
        except Exception:
            _hermes_overrides_set = False
        (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        incomplete_final_response = False
        try:
            loop = asyncio.get_event_loop()
            run_context = contextvars.copy_context()

            async def _run_turn(user_message: str, conversation_history: list[Dict[str, Any]]) -> Dict[str, Any]:
                return await loop.run_in_executor(
                    _AGENT_EXECUTOR,
                    lambda: run_context.run(
                        lambda: agent.run_conversation(
                            user_message=user_message,
                            conversation_history=conversation_history,
                            task_id=sid,
                        )
                    ),
                )

            def _normalize_final_text(raw_response: Dict[str, Any]) -> tuple[str, bool]:
                resolved_text = (raw_response.get("final_response") or "").strip()
                if not resolved_text and latest_useful_tool_output:
                    logger.info(
                        "[%s] using tool-result fallback for empty final response",
                        sid[:8],
                    )
                    return latest_useful_tool_output.strip(), False

                is_incomplete = self._looks_incomplete_final_response(resolved_text)
                if is_incomplete and latest_useful_tool_output and saw_successful_file_mutation and not is_backtest_task:
                    logger.warning(
                        "[%s] using file-tool fallback for incomplete final response: %s",
                        sid[:8],
                        resolved_text[:200],
                    )
                    return latest_useful_tool_output.strip(), False

                return resolved_text, is_incomplete

            raw = await _run_turn(attempt.prompt, history)
            final_text, incomplete_final_text = _normalize_final_text(raw)
            incomplete_response_retry = False

            if incomplete_final_text and not is_backtest_task:
                incomplete_response_retry = True
                retry_message = (
                    f"Agent response was incomplete and auto-retried. "
                    f"Initial incomplete response: {final_text[:200]}"
                )
                logger.warning(
                    "[%s] retrying once after incomplete final response: %s",
                    sid[:8],
                    final_text[:200],
                )
                retry_history = [
                    *history,
                    {"role": "assistant", "content": final_text},
                    {"role": "user", "content": _INCOMPLETE_RESPONSE_RETRY_PROMPT},
                ]
                raw = await _run_turn(_INCOMPLETE_RESPONSE_RETRY_PROMPT, retry_history)
                final_text, incomplete_final_text = _normalize_final_text(raw)

            if incomplete_final_text:
                incomplete_final_response = True
                logger.warning(
                    "[%s] treating incomplete final response as failed attempt: %s",
                    sid[:8],
                    final_text[:200],
                )
                result = {
                    "status": "failed",
                    "reason": "Agent returned an incomplete response and stopped before completing the requested action.",
                    "content": "",
                    "run_dir": str(run_dir),
                    "run_id": run_dir.name,
                }
            else:
                final_text, ui_schema = self._extract_a2ui_schema_from_text(final_text)
                # Persist assistant markdown for every successful response so the
                # run directory always has a user-visible report artifact.
                if final_text:
                    try:
                        (run_dir / "report.md").write_text(final_text, encoding="utf-8")
                    except Exception:
                        logger.warning("Failed to persist report.md for run_dir=%s", run_dir, exc_info=True)
                result: Dict[str, Any] = {
                    "status": "success",
                    "content": final_text,
                    "run_dir": str(run_dir),
                    "run_id": run_dir.name,
                }
                if ui_schema:
                    result["ui_schema"] = ui_schema
                if incomplete_response_retry:
                    result["retry_message"] = (
                        f"Agent response was incomplete and auto-retried. "
                        f"Initial response: {final_text[:100]}..."
                    )
        except Exception as exc:
            logger.error("[%s] agent exception in run_dir=%s: %s", sid[:8], run_dir, exc, exc_info=True)
            state_store.mark_failure(run_dir, str(exc))
            result = {
                "status": "cancelled" if self._is_cancelled_error(str(exc)) else "failed",
                "reason": str(exc),
                "content": "",
                "run_dir": str(run_dir),
                "run_id": run_dir.name,
            }
        finally:
            reset_session_runs_dir(_runs_token)
            if _swarm_token is not None:
                reset_session_swarm_dir(_swarm_token)
            if _hermes_overrides_set:
                try:
                    clear_task_env_overrides(sid)
                except Exception:
                    pass
            self._active_loops.pop(sid, None)
            if hermes_home_token is not None:
                reset_active_hermes_home(hermes_home_token)

        # Load metrics from the run output when available.
        actual_run_dir = latest_backtest_run_dir or latest_prepared_run_dir or result.get("run_dir")
        if actual_run_dir:
            result["run_dir"] = actual_run_dir
            result["run_id"] = Path(actual_run_dir).name
            self.store.register_artifact(sid, str(actual_run_dir), kind="run_dir")
            metrics = self._load_metrics(Path(actual_run_dir))
            if metrics:
                result["metrics"] = metrics

        backtest_completed = saw_successful_backtest or bool(result.get("metrics"))
        final_run_dir = Path(result.get("run_dir") or run_dir)

        if result.get("status") == "failed" and incomplete_final_response and is_backtest_task and backtest_completed:
            fallback_report = build_backtest_report(
                final_run_dir,
                prompt=attempt.prompt,
                metrics=result.get("metrics"),
            )
            if fallback_report:
                try:
                    (final_run_dir / "report.md").write_text(fallback_report, encoding="utf-8")
                except Exception:
                    logger.warning("Failed to persist synthesized report.md for run_dir=%s", final_run_dir, exc_info=True)
                result["status"] = "success"
                result["content"] = fallback_report
                result.pop("reason", None)

        result["has_run_artifact"] = self._has_run_artifact(
            result.get("run_dir"),
            result.get("metrics"),
        )

        if result.get("status") == "success" and is_backtest_task:
            if not backtest_completed:
                result["status"] = "failed"
                result["reason"] = (
                    "Backtest run did not complete successfully; no successful backtest tool execution or metrics were produced."
                )
                result["content"] = ""

        if result.get("status") == "success":
            state_store.mark_success(run_dir)
            if final_run_dir != run_dir:
                try:
                    state_store.mark_success(final_run_dir)
                except Exception:
                    pass
        else:
            failure_reason = str(result.get("reason", "unknown"))
            state_store.mark_failure(run_dir, failure_reason)
            if final_run_dir != run_dir:
                try:
                    state_store.mark_failure(final_run_dir, failure_reason)
                except Exception:
                    pass

        return result

    @staticmethod
    def _has_run_artifact(
        run_dir: Optional[str],
        metrics: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Return whether a run has a user-visible artifact worth linking."""
        if metrics:
            return True
        if not run_dir:
            return False

        base = Path(run_dir)
        artifact_paths = [
            base / "report.md",
            base / "summary.md",
            base / "answer.md",
            base / "final_report.md",
            base / "final_report.txt",
            base / "artifacts" / "metrics.csv",
        ]
        return any(path.exists() and path.is_file() for path in artifact_paths)

    @staticmethod
    def _convert_messages_to_history(messages: list) -> list[Dict[str, Any]]:
        """Convert Session messages into OpenAI-format history.

        Keeps the readable ``[prev_run: {run_id}]`` marker instead of removing it
        completely, and trims by character budget instead of a hard six-message cap
        so the LLM can still see previous artifact paths and strategy content during
        iterative updates.

        Args:
            messages: Session message list without the current turn.

        Returns:
            OpenAI-format messages trimmed from the newest items within the token budget.
        """
        import re
        from pathlib import Path

        def _shorten_run_dir(match: re.Match) -> str:
            path_str = match.group(0).replace("Run directory:", "").strip()
            run_id = Path(path_str).name if path_str else ""
            return f"[prev_run: {run_id}]" if run_id else ""

        history = []
        for msg in messages[:-1]:
            role = msg.role if hasattr(msg, "role") else msg.get("role", "user")
            content = msg.content if hasattr(msg, "content") else msg.get("content", "")
            if not content.strip() or role not in ("user", "assistant"):
                continue
            content = re.sub(r"Run directory:\s*\S+", _shorten_run_dir, content).strip()
            if content:
                history.append({"role": role, "content": content})

        # Trim from the newest messages within a character budget of roughly 3000 tokens.
        MAX_HISTORY_CHARS = 12000
        total_chars = 0
        trimmed: list = []
        for msg in reversed(history):
            msg_len = len(msg.get("content", ""))
            if total_chars + msg_len > MAX_HISTORY_CHARS:
                break
            trimmed.append(msg)
            total_chars += msg_len
        return list(reversed(trimmed))

    @staticmethod
    def _load_metrics(run_dir: Path) -> Optional[Dict[str, Any]]:
        """Load metrics.csv from a run directory."""
        import csv
        metrics_path = run_dir / "artifacts" / "metrics.csv"
        if not metrics_path.exists():
            return None
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
                if rows:
                    return {k: float(v) for k, v in rows[0].items() if v}
        except Exception:
            pass
        return None

    @staticmethod
    def _is_reportable_tool_result(tool_name: str, parsed_result: Optional[Dict[str, Any]]) -> bool:
        """Return whether a successful tool result is user-reportable on its own."""
        data = parsed_result if isinstance(parsed_result, dict) else {}
        if tool_name == "read_document":
            status = str(data.get("status") or "").strip().lower()
            return status in {"ok", "success"} and any(
                isinstance(data.get(key), str) and data.get(key, "").strip()
                for key in ("text", "summary", "report", "message", "analysis", "file")
            )
        return False

    @staticmethod
    def _extract_useful_tool_output(
        tool_name: str,
        parsed_result: Optional[Dict[str, Any]],
        preview: str,
    ) -> str:
        """Extract readable fallback content from a successful tool result."""
        data = parsed_result if isinstance(parsed_result, dict) else {}

        if tool_name in _FILE_MUTATION_TOOL_NAMES:
            if tool_name == "delete_file":
                return "File deletion completed successfully."
            if tool_name == "mkdir":
                return "Directory creation completed successfully."
            return "File update completed successfully."

        if tool_name == "run_swarm":
            final_report = str(data.get("final_report") or "").strip()
            if final_report:
                return final_report

            task_sections: list[str] = []
            tasks = data.get("tasks") or []
            if isinstance(tasks, list):
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    summary = str(task.get("summary") or "").strip()
                    if not summary:
                        continue
                    agent_id = str(task.get("agent_id") or task.get("id") or "task").strip()
                    task_sections.append(f"### {agent_id}\n{summary}")
            if task_sections:
                return "\n\n".join(task_sections)

        for key in ("summary", "report", "message", "analysis"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        clean_preview = str(preview or "").strip()
        if clean_preview and not clean_preview.startswith(("{", "[")):
            return clean_preview[:4000]

        return ""

    @staticmethod
    def _format_result_message(attempt: Attempt) -> str:
        """Format the final execution result message."""
        if attempt.status == AttemptStatus.COMPLETED:
            base_message = attempt.summary or "Strategy execution completed."
        else:
            base_message = f"Execution failed: {attempt.error or 'unknown error'}"

        run_dir = (attempt.run_dir or "").strip()
        if not run_dir:
            return base_message

        run_id = Path(run_dir).name.strip()
        if not run_id:
            return base_message

        if "/runs/" in base_message and run_id in base_message:
            return base_message

        # Keep a stable report entry-point for chat replies and include the
        # absolute run directory to make filesystem artifacts discoverable.
        return (
            f"{base_message}\n\n"
            f"[Full report](/runs/{run_id})\n\n"
            f"Run directory: {run_dir}"
        )
