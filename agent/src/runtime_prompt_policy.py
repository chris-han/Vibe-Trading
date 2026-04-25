"""Shared runtime prompt policy fragments for Hermes-based agent runtimes."""

from __future__ import annotations

import logging
from pathlib import Path

from src.upload_capabilities import format_supported_upload_extensions


logger = logging.getLogger(__name__)


def _format_rules(title: str, rules: tuple[str, ...]) -> str:
    return title + ":\n" + "\n".join(f"- {rule}" for rule in rules) + "\n"


_BACKTEST_WORKFLOW_RULES = (
    "Apply these backtest workflow rules only when the user's request is explicitly about trading strategy generation, backtesting, or run_dir/config/signal_engine troubleshooting.",
    "For unrelated tasks (for example docs or general coding), do not call setup_backtest_run(...) or backtest(...).",
    "Never use setup_backtest_run(...) + backtest(...) as a workaround to execute arbitrary Python for non-backtest tasks.",
    "If the user asks for a new backtest or strategy test, do NOT call backtest(run_dir=...) first.",
    'First call skill_view(name="strategy-generate") when you need the SignalEngine contract.',
    "Pass config_json and signal_engine_py directly to setup_backtest_run(...); do not manually create run directories or write the run files yourself.",
    "Only after setup_backtest_run succeeds, call backtest(run_dir=...).",
    "If a backtest fails because generated strategy code is wrong, prefer a fresh setup_backtest_run(...) before retrying.",
    "Do not use delegate_task to discover or import setup_backtest_run/backtest from the repository source code.",
    "If you delegate backtest-related work, do not restrict the child to terminal/file-only toolsets; omit toolsets or include the runtime's finance/backtest toolset so the child can call setup_backtest_run(...) and backtest(...).",
)

def _document_workflow_rules() -> tuple[str, ...]:
    supported_types = format_supported_upload_extensions()
    return (
        "Refer to the current workspace upload area shown above for all user-provided report paths.",
        f"Uploaded document types accepted by this runtime: {supported_types}.",
        'For generic document/file-format capability questions or non-PDF office documents, call skill_view(name="ocr-and-documents") before answering from the raw tool list.',
        "For DOCX, XLSX, or similar local document formats, prefer the relevant loaded skill guidance before concluding whether the runtime can read them.",
        "If the user provides an uploaded document reference, prefer the relevant reader for that local file path.",
        "Never invent an uploaded filename; only call a local document reader when the exact local path is known.",
        "If the filename is unknown, ask for the uploaded filename or inspect only the current workspace upload area with non-terminal file tools before searching elsewhere.",
        "Never use terminal ls/cd commands against the /workspace upload alias shown above; that uploads path is a virtual display alias, not a terminal cwd target.",
        "Never search Desktop, Downloads, /mnt, or other host filesystem locations for uploaded documents.",
        "If no local path is available, use read_url or browser tools to fetch the report from the source site.",
        "Prefer reading the first relevant pages first with pages='1-5' when the document is long.",
        "Treat low-text PDF pages as scanned/image pages; OCR is optional and controlled by HERMES_ENABLE_PDF_OCR.",
        "Do not claim you cannot read supported uploaded documents when the relevant reader tool or loaded skill is available.",
    )

_MARKET_DATA_WORKFLOW_RULES = (
    "For finance or research tasks, call skill_view(name=...) first to get approved data access methods and symbol conventions.",
    "For creating, installing, editing, patching, or deleting skills, use skill_manage instead of terminal commands or general file-editing tools.",
    "When creating multiple skills in a single request, create at most 2 skills per turn, then stop and summarize what was created. Resume creating the remaining skills only when explicitly asked to continue. This prevents output truncation from hitting model token limits.",
    "This runtime runs on Linux. Supported package managers are: npm/npx, pip, uv pip, uv tool, pnpm, bun, yarn, cargo, go install, apt/apt-get. Do NOT use macOS-only or unsupported package managers (brew, port, pkg, scoop, choco, winget, gem standalone); if a skill or instruction calls for one, reject the step and inform the user it is not supported in this environment.",
    "Before installing any external CLI tool via a supported package manager (npm install -g, pip install, uv pip install, uv tool install, pnpm add -g, bun add -g, yarn global add, cargo install, go install, apt install), ALWAYS check if the tool is already installed first (e.g. `<tool> --version` or `which <tool>`). If already installed, skip the install step entirely and proceed with configuration.",
    "If skill_view returns a skill successfully, treat the CLI described in that skill as potentially already installed; verify with a version check before running any package manager install.",
    "In this runtime, if the user asks for a global install, admin-home install, or user-level skill install, interpret that as the active HERMES_HOME/skills directory.",
    "User-generated skills belong in the active workspace HERMES_HOME/skills directory, not in the current run or artifacts directory.",
    "Hermes skill registry installation (e.g. `npx skills add`, `skills install`) enforces the upstream override hierarchy: bundled skills > external configured skills > workspace local skills. Terminal Hermes-skill-registry commands and file writes to .agents/skills or HERMES_HOME/skills are blocked by the runtime; use skill_manage tool or skills API endpoint instead. This restriction applies only to Hermes skill management — installing external CLI tools or npm packages via `npm install -g <package>` is a normal terminal operation and is NOT blocked.",
    "Never install skills to `~/.agents/skills`; all skill installations are restricted to the active HERMES_HOME/skills directory only. To configure custom skill directories, edit external_dirs in ~/.hermes/config.yaml.",
    "Do not create or modify files under .hermes/skills directly with general file-editing tools; relative .hermes/skills paths resolve inside the active run/artifacts sandbox. Use skill_manage for skill creation and editing.",
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
DOCUMENT_WORKFLOW_PROMPT = _format_rules("Document workflow rules", _document_workflow_rules())
MARKET_DATA_WORKFLOW_PROMPT = _format_rules("Market data workflow rules", _MARKET_DATA_WORKFLOW_RULES)

OUTPUT_FORMAT_PROMPT = _format_rules(
    "Output format rules",
    (
        "Prefer Markdown, Mermaid, and structured chart blocks for rich visual output.",
        "When asking users for multiple structured inputs, emit one fenced ```a2ui JSON block with a root component 'schema_form' and props.fields (key, label, type, required, placeholder), then provide brief plain-language guidance.",
        "If the active skill defines an explicit A2UI/schema_form contract for missing inputs, follow that schema exactly instead of inventing new field labels or paraphrasing instruction text into fields.",
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
    candidate_files = [
        skills_dir / skill_name / "SKILL.md",
        skills_dir / "domain" / "vibe-trading" / skill_name / "SKILL.md",
    ]
    skill_file = None
    for candidate in candidate_files:
        if candidate.exists() and candidate.is_file():
            skill_file = candidate
            break

    if skill_file is None:
        # Last resort: resolve by directory name anywhere under skills/.
        for nested in skills_dir.rglob("SKILL.md"):
            if nested.parent.name == skill_name:
                skill_file = nested
                break

    if skill_file is None:
        logger.warning("output-format skill not found: %s", candidate_files[0])
        return ""

    try:
        text = skill_file.read_text(encoding="utf-8")
    except Exception:
        logger.warning("output-format skill not readable: %s", skill_file)
        return ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    return text.strip()


_ADMIN_INSTALL_RULES = _format_rules(
    "System-level install rules (administrator only)",
    (
        "This session has administrator privileges.",
        "System-level package managers (apt/apt-get) are permitted for installing system dependencies.",
        "Prefer apt-get over apt for non-interactive scripting. Always pass -y to avoid prompts.",
    ),
)

_REGULAR_USER_INSTALL_RULES = _format_rules(
    "Install scope rules (regular user)",
    (
        "This session does NOT have administrator privileges.",
        "System-level package managers (apt, apt-get) are FORBIDDEN. If a task requires them, reject the step and tell the user to ask an administrator.",
        "Allowed package managers are limited to user-space tools: npm/npx, pip, uv pip, uv tool, pnpm, bun, yarn, cargo, go install — scoped to the active workspace only.",
        "Do not attempt to install system libraries, kernel modules, or any package requiring root/sudo access.",
        "For skill and agent tool installation, use skill_manage targeting the workspace HERMES_HOME/skills directory only.",
    ),
)


def build_session_runtime_prompt(
    run_dir: str,
    session_id: str,
    channel: str,
    *,
    sandbox_role: str = "regular_user",
    display_workspace_root: str | None = None,
    display_run_dir: str | None = None,
    display_artifacts_dir: str | None = None,
) -> str:
    """Build the Hermes ephemeral prompt used by interactive session runs."""
    visible_workspace_root = display_workspace_root or SESSION_VIRTUAL_WORKSPACE_ROOT
    visible_run_dir = display_run_dir or run_dir
    visible_artifacts_dir = display_artifacts_dir or f"{visible_run_dir.rstrip('/')}/artifacts"
    visible_uploads_dir = f"{visible_workspace_root.rstrip('/')}/sessions/{session_id}/uploads"
    role_install_rules = _ADMIN_INSTALL_RULES if sandbox_role == "administrator" else _REGULAR_USER_INSTALL_RULES
    return (
        f"Run directory: {visible_run_dir}\n"
        f"Session workspace: {visible_workspace_root}\n"
        f"Artifacts directory: {visible_artifacts_dir}\n"
        f"Uploads directory: {visible_uploads_dir}\n"
        "Use relative paths for terminal work.\n"
        "Use the Uploads directory alias only with file-style tools, not terminal commands.\n"
        "Use /workspace and /workspace/run only as virtual display aliases for file-style tools, not terminal cwd targets.\n"
        "Do not rely on host absolute paths.\n"
        f"Session: {session_id}\n"
        f"{role_install_rules}"
        f"{BACKTEST_WORKFLOW_PROMPT}"
        f"{DOCUMENT_WORKFLOW_PROMPT}"
        f"{MARKET_DATA_WORKFLOW_PROMPT}"
        f"{OUTPUT_FORMAT_PROMPT}"
        f"{load_output_format_skill(channel)}\n"
    )
