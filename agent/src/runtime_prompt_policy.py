"""Shared runtime prompt policy fragments for Hermes-based agent runtimes."""

from __future__ import annotations

import logging
from pathlib import Path


logger = logging.getLogger(__name__)


def _format_rules(title: str, rules: tuple[str, ...]) -> str:
    return title + ":\n" + "\n".join(f"- {rule}" for rule in rules) + "\n"


_BACKTEST_WORKFLOW_RULES = (
    "If the user asks for a new backtest or strategy test, do NOT call backtest(run_dir=...) first.",
    'First call skill_view(name="strategy-generate") when you need the SignalEngine contract.',
    "Pass config_json and signal_engine_py directly to setup_backtest_run(...); do not manually create run directories or write the run files yourself.",
    "Only after setup_backtest_run succeeds, call backtest(run_dir=...).",
    "If a backtest fails because generated strategy code is wrong, prefer a fresh setup_backtest_run(...) before retrying.",
)

_DOCUMENT_WORKFLOW_RULES = (
    "Refer to the current workspace upload area shown above for all user-provided report paths.",
    "If the user provides an uploaded PDF reference, prefer read_document(file_path=...) to extract it.",
    "Never invent a PDF filename; only call read_document when the exact local path is known.",
    "If the filename is unknown, list the Uploads directory shown above for candidate PDFs before searching elsewhere.",
    "Never search Desktop, Downloads, /mnt, or other host filesystem locations for uploaded documents.",
    "If no local path is available, use read_url or browser tools to fetch the report from the source site.",
    "Prefer reading the first relevant pages first with pages='1-5' when the document is long.",
    "Treat low-text pages as scanned/image pages; OCR is optional and controlled by HERMES_ENABLE_PDF_OCR.",
    "Do not claim you cannot read PDFs when read_document is available.",
)

_MARKET_DATA_WORKFLOW_RULES = (
    "For finance or research tasks, call skill_view(name=...) first to get approved data access methods and symbol conventions.",
    "For creating, editing, patching, or deleting skills, use skill_manage instead of general file-editing tools.",
    "User-generated skills belong in the active workspace HERMES_HOME/skills directory, not in the current run or artifacts directory.",
    "Do not create or modify files under .hermes/skills directly with general file-editing tools; relative .hermes/skills paths resolve inside the active run/artifacts sandbox.",
    "execute_code is forbidden in this runtime.",
    "Do NOT fetch market data with curl, ad hoc HTTP endpoints, or raw requests scripts.",
    "When you need current news, policy documents, or source pages and the exact URL is not already known, use the Hermes web_search tool first to find the canonical source.",
    "After web_search finds the source URL, use read_url to fetch the full page content. Do not rely on provider-native search or built-in model browsing.",
    "Use the project-supported Python patterns from load_skill (for example yfinance or OKX API helpers).",
    "For interactive session terminal commands, use python3 from the preconfigured session environment for script execution.",
    "Do NOT assume .venv exists under the current run directory or use host absolute interpreter paths.",
    "For package installs, use python3 -m pip. Do NOT call pip/pip3 directly.",
    "Do NOT embed long Python programs directly in bash commands.",
    "The terminal already starts inside the run artifacts directory; prefer relative paths over any cd command.",
    "Treat /workspace and /workspace/run as display aliases for file-style tools, not terminal cwd targets.",
    "Do NOT cd to /workspace or /workspace/run in terminal commands; use relative paths from the current cwd instead.",
    "If an external endpoint or symbol looks suspicious, validate it against the loaded skill before using it.",
)


BACKTEST_WORKFLOW_PROMPT = _format_rules("Backtest workflow rules", _BACKTEST_WORKFLOW_RULES)
DOCUMENT_WORKFLOW_PROMPT = _format_rules("Document workflow rules", _DOCUMENT_WORKFLOW_RULES)
MARKET_DATA_WORKFLOW_PROMPT = _format_rules("Market data workflow rules", _MARKET_DATA_WORKFLOW_RULES)

OUTPUT_FORMAT_PROMPT = _format_rules(
    "Output format rules",
    (
        "Prefer Markdown, Mermaid, and structured chart blocks for rich visual output.",
        "Render tables as Markdown pipe-tables.",
        "Use Mermaid for diagrams and flowcharts.",
        "For Mermaid, the first line inside the fence MUST be a supported diagram keyword such as graph TD, flowchart TD, sequenceDiagram, classDiagram, stateDiagram-v2, erDiagram, gantt, pie, timeline, mindmap, or gitGraph.",
        "Do not invent Mermaid openers like top-down or left-right, and do not guess unsupported diagram types.",
        "If a Mermaid diagram would require unsupported or uncertain syntax, fall back to Markdown bullets or a Markdown table.",
        "Use echarts blocks for charts in the web UI.",
        "For Feishu or other constrained channels, follow the channel-specific chart rules instead of the web rule.",
        "If unsure, fall back to a Markdown table rather than emitting a chart fence.",
        "Never use ANSI art or terminal box-drawing characters.",
        "Keep visual output Markdown-native so it renders cleanly across channels.",
    ),
)

SESSION_VIRTUAL_WORKSPACE_ROOT = "/workspace"
SESSION_VIRTUAL_RUN_DIR = f"{SESSION_VIRTUAL_WORKSPACE_ROOT}/run"
SESSION_VIRTUAL_ARTIFACTS_DIR = f"{SESSION_VIRTUAL_RUN_DIR}/artifacts"


def load_output_format_skill(channel: str) -> str:
    """Load the channel-appropriate output-format skill body from its SKILL.md file."""
    skill_name = "output-format-feishu" if channel == "feishu" else "output-format-web"
    skills_dir = Path(__file__).resolve().parent / "skills"
    skill_file = skills_dir / skill_name / "SKILL.md"
    try:
        text = skill_file.read_text(encoding="utf-8")
    except Exception:
        logger.warning("output-format skill not found: %s", skill_file)
        return ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return text.strip()


def build_session_runtime_prompt(
    run_dir: str,
    session_id: str,
    channel: str,
    *,
    display_workspace_root: str | None = None,
    display_run_dir: str | None = None,
    display_artifacts_dir: str | None = None,
) -> str:
    """Build the Hermes ephemeral prompt used by interactive session runs."""
    visible_workspace_root = display_workspace_root or SESSION_VIRTUAL_WORKSPACE_ROOT
    visible_run_dir = display_run_dir or run_dir
    visible_artifacts_dir = display_artifacts_dir or f"{visible_run_dir.rstrip('/')}/artifacts"
    visible_uploads_dir = f"{visible_workspace_root.rstrip('/')}/sessions/{session_id}/uploads"
    return (
        f"Session workspace: {visible_workspace_root}\n"
        f"Run directory: {visible_run_dir}\n"
        f"Artifacts directory: {visible_artifacts_dir}\n"
        f"Uploads directory: {visible_uploads_dir}\n"
        "Use relative paths for terminal work.\n"
        "Use /workspace and /workspace/run only as virtual display aliases for file-style tools, not terminal cwd targets.\n"
        "Do not rely on host absolute paths.\n"
        f"Session: {session_id}\n"
        f"{BACKTEST_WORKFLOW_PROMPT}"
        f"{DOCUMENT_WORKFLOW_PROMPT}"
        f"{MARKET_DATA_WORKFLOW_PROMPT}"
        f"{OUTPUT_FORMAT_PROMPT}"
        f"{load_output_format_skill(channel)}\n"
    )
