"""Swarm Worker: executes per-task agents using Hermes AIAgent."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from runtime_env import ensure_runtime_env, get_hermes_agent_kwargs, prepare_hermes_project_context
from src.swarm.models import (
    SwarmAgentSpec,
    SwarmEvent,
    SwarmTask,
    WorkerResult,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITERATIONS = 50
_BACKTEST_WORKFLOW_HINT = (
    "- For any new backtest, call `setup_backtest_run(config_json=..., signal_engine_py=...)` before `backtest(run_dir=...)`.\n"
    "- Never ask the user to create `config.json` or `code/signal_engine.py` manually when the setup tool can write them.\n"
)

_DOCUMENT_WORKFLOW_HINT = (
    "- If the task includes an exact local PDF path, call `read_document(file_path=...)` before summarizing the document.\n"
    "- Never invent a PDF filename; only call `read_document` when the exact path is known.\n"
    "- If no local path is available, use read_url or browser tools to fetch the report from the source site.\n"
    "- If no local path is available, use `read_url` or browser tools to fetch the report from the source site.\n"
    "- Prefer targeted page ranges first for long filings or reports.\n"
    "- OCR is feature-flagged through `HERMES_ENABLE_PDF_OCR` and may be unavailable.\n"
)

_MARKET_DATA_WORKFLOW_HINT = (
    "- `execute_code` is forbidden in this runtime. Use `write_file` plus `bash` with the runtime-provided cwd instead.\n"
    "- **NEVER use curl/requests/urllib to fetch market data.** Call `load_skill('yfinance')` first, then write a Python script.\n"
    "- Never hardcode output file paths such as `/app/agent/...` or `agent/...`; keep outputs relative so Hermes stores them under the task artifact directory.\n"
)


def _emit(
    callback: Callable[[SwarmEvent], None] | None,
    event_type: str,
    agent_id: str,
    task_id: str,
    data: dict | None = None,
) -> None:
    """Emit a swarm event via callback if provided.

    Args:
        callback: Optional event callback function.
        event_type: Event type string.
        agent_id: Agent identifier.
        task_id: Task identifier.
        data: Additional event data.
    """
    if callback is None:
        return
    event = SwarmEvent(
        type=event_type,
        agent_id=agent_id,
        task_id=task_id,
        data=data or {},
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    try:
        callback(event)
    except Exception:
        logger.warning("Event callback failed for %s", event_type, exc_info=True)


def _format_skill_hint(skill_names: list[str]) -> str:
    """Return a brief skill menu for the system prompt.

    Full skill content is loaded on-demand by the Hermes load_skill tool.

    Args:
        skill_names: Skill names from the agent spec whitelist.

    Returns:
        Formatted hint string.
    """
    if not skill_names:
        return "(use skills_list to discover available finance skills)"
    return "\n".join(f"  - {name}" for name in skill_names)


def build_worker_prompt(
    agent_spec: SwarmAgentSpec,
    upstream_summaries: dict[str, str],
    skill_hint: str,
) -> str:
    """Build the worker's system prompt with role, upstream context, and skill hints.

    Args:
        agent_spec: The agent's role specification.
        upstream_summaries: Mapping of context_key -> upstream task summary.
        skill_hint: Brief list of relevant skill names for this worker.

    Returns:
        Complete system prompt string for the worker LLM.
    """
    upstream_block = ""
    if upstream_summaries:
        sections = []
        for key, summary in upstream_summaries.items():
            sections.append(f"### {key}\n{summary}")
        upstream_block = (
            "## Upstream Context (from previous agents)\n\n"
            + "\n\n".join(sections)
        )

    prompt_parts = [
        f"## Role\n\n{agent_spec.role}",
        agent_spec.system_prompt.replace("{upstream_context}", upstream_block),
    ]

    if skill_hint:
        prompt_parts.append(
            f"## Available Finance Skills (use load_skill <name> to access full documentation)\n\n{skill_hint}"
        )

    prompt_parts.append(
        "## Execution Rules\n\n"
        "You have a HARD LIMIT of 20 tool calls. After that you will be cut off. Work efficiently.\n\n"
        "**Phase 1 — Plan (0 tool calls):** Before calling any tool, state your plan in 3-5 bullet points.\n\n"
        "**Phase 2 — Execute (≤15 tool calls):**\n"
        "- `load_skill` first to get data access methods and analysis patterns.\n"
        f"{_MARKET_DATA_WORKFLOW_HINT}"
        "- Prefer writing one focused Python script with write_file, then execute it with bash.\n"
        "- Write ONE focused Python script via `write_file`, then run it from the current runtime cwd with `./.venv/bin/python`.\n"
        "- Install packages with `./.venv/bin/python -m pip`. Do NOT call `pip` or `pip3` directly.\n"
        "- Do NOT write long Python code inside bash. Use write_file + bash.\n"
        "- Do NOT fetch data with curl/requests. Use the patterns from load_skill (yfinance, OKX API via Python).\n"
        f"{_BACKTEST_WORKFLOW_HINT}"
        f"{_DOCUMENT_WORKFLOW_HINT}"
        "- If a script fails, read the error, fix with `edit_file`, re-run. Max 2 retries per script.\n\n"
        "**Phase 3 — Summarize (0 tool calls):**\n"
        "- Write your final findings as a concise markdown summary directly in your response.\n"
        "- Include specific numbers, dates, and actionable conclusions.\n"
        "- Respond in the same language as the task prompt."
    )

    return "\n\n".join(prompt_parts)


def run_worker(
    agent_spec: SwarmAgentSpec,
    task: SwarmTask,
    upstream_summaries: dict[str, str],
    user_vars: dict[str, str],
    run_dir: Path,
    event_callback: Callable[[SwarmEvent], None] | None = None,
) -> WorkerResult:
    """Execute a single worker task using Hermes AIAgent.

    Args:
        agent_spec: Agent role specification with tools/skills/model config.
        task: The task to execute, including prompt template.
        upstream_summaries: Summaries from upstream tasks keyed by input_from keys.
        user_vars: User-provided variables for template rendering.
        run_dir: Path to .swarm/runs/{run_id}/ directory.
        event_callback: Optional callback for swarm events.

    Returns:
        WorkerResult with status, summary, artifacts, and iteration count.
    """
    import os
    import sys
    prepare_hermes_project_context(chdir=True)
    _HERMES = Path(__file__).resolve().parents[3] / "hermes-agent"
    if str(_HERMES) not in sys.path:
        sys.path.insert(0, str(_HERMES))
    from run_agent import AIAgent

    agent_id = agent_spec.id
    task_id = task.id
    max_iterations = agent_spec.max_iterations or _DEFAULT_MAX_ITERATIONS

    _emit(event_callback, "worker_started", agent_id, task_id)

    # Resolve prompt template with user vars
    try:
        user_prompt = task.prompt_template.format(**user_vars)
    except KeyError as exc:
        error_msg = f"Missing variable in prompt template: {exc}"
        _emit(event_callback, "worker_failed", agent_id, task_id, {"error": error_msg})
        return WorkerResult(
            status="failed", summary="", iterations=0, error=error_msg,
            input_tokens=0, output_tokens=0,
        )

    artifact_dir = run_dir / "artifacts" / agent_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Build system prompt with role and upstream context
    skill_hint = _format_skill_hint(agent_spec.skills)
    system_prompt = build_worker_prompt(agent_spec, upstream_summaries, skill_hint)

    # Wire Hermes callbacks to swarm events
    def _on_tool_progress(event_type: str, tool_name: str, preview: str, args: dict, **kwargs) -> None:
        if event_type == "tool.started":
            _emit(event_callback, "tool_call", agent_id, task_id,
                  {"tool": tool_name, "args": args or {}})
        elif event_type == "tool.completed":
            _emit(event_callback, "tool_result", agent_id, task_id,
                  {"tool": tool_name, "is_error": kwargs.get("is_error", False)})

    def _on_stream_delta(delta: str | None) -> None:
        if delta:
            _emit(event_callback, "worker_text", agent_id, task_id, {"content": delta})

    def _on_tool_generation(tool_name: str) -> None:
        if tool_name == "execute_code":
            logger.error(
                "Worker %s/%s permission_denied execute_code attempted by model; "
                "toolset is disabled for Vibe-Trading swarm runtime",
                agent_id,
                task_id,
            )

    ensure_runtime_env()
    agent_kwargs = get_hermes_agent_kwargs()

    agent = AIAgent(
        model=agent_spec.model_name or os.getenv("HERMES_MODEL", ""),
        max_iterations=max_iterations,
        quiet_mode=True,
        session_id=f"swarm-{agent_id}-{task_id}",
        enabled_toolsets=[
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
        ],
        disabled_toolsets=["code_execution"],
        tool_progress_callback=_on_tool_progress,
        tool_gen_callback=_on_tool_generation,
        stream_delta_callback=_on_stream_delta,
        ephemeral_system_prompt=system_prompt,
        skip_context_files=True,
        **agent_kwargs,
    )

    # Configure hermes built-in file/terminal tools to write into the artifact dir.
    try:
        from tools.terminal_tool import register_task_env_overrides, clear_task_env_overrides
        register_task_env_overrides(str(task_id), {"cwd": str(artifact_dir)})
        _hermes_overrides_set = True
    except Exception:
        _hermes_overrides_set = False
    try:
        raw = agent.run_conversation(user_message=user_prompt, task_id=str(task_id))
        summary = (raw.get("final_response") or "").strip()
        _write_summary(artifact_dir, summary)
        _emit(event_callback, "worker_completed", agent_id, task_id)
        return WorkerResult(
            status="completed",
            summary=summary,
            artifact_paths=_collect_artifacts(artifact_dir),
            iterations=raw.get("iterations", 0),
            input_tokens=raw.get("input_tokens", 0),
            output_tokens=raw.get("output_tokens", 0),
        )
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("Worker %s failed: %s", agent_id, error_msg, exc_info=True)
        _emit(event_callback, "worker_failed", agent_id, task_id, {"error": error_msg})
        return WorkerResult(
            status="failed",
            summary="",
            artifact_paths=_collect_artifacts(artifact_dir),
            iterations=0,
            error=error_msg,
            input_tokens=0, output_tokens=0,
        )
    finally:
        if _hermes_overrides_set:
            try:
                clear_task_env_overrides(str(task_id))
            except Exception:
                pass


def _write_summary(artifact_dir: Path, summary: str) -> None:
    """Write worker summary to artifacts directory.

    Args:
        artifact_dir: Path to artifacts/{agent_id}/ directory.
        summary: Summary text to write.
    """
    try:
        summary_path = artifact_dir / "summary.md"
        summary_path.write_text(summary, encoding="utf-8")
    except Exception:
        logger.warning("Failed to write summary to %s", artifact_dir, exc_info=True)


def _collect_artifacts(artifact_dir: Path) -> list[str]:
    """Collect all artifact file paths from agent's artifact directory.

    Args:
        artifact_dir: Path to artifacts/{agent_id}/ directory.

    Returns:
        List of artifact file path strings.
    """
    if not artifact_dir.exists():
        return []
    return [str(p) for p in artifact_dir.iterdir() if p.is_file()]
