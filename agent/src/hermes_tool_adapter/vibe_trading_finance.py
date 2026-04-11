"""Vibe-Trading finance tool definitions for Hermes runtime plugins."""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_AGENT_ROOT = Path(__file__).resolve().parents[2]
_HERMES_ROOT = _AGENT_ROOT.parent / "hermes-agent"

if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))
if _HERMES_ROOT.exists() and str(_HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(_HERMES_ROOT))


def _setup_backtest_run(args: dict, **_) -> str:
    """Create a timestamped run directory and write config.json + signal_engine.py."""
    try:
        import uuid
        from datetime import datetime

        base_dir = Path(args.get("base_dir", "")).expanduser()
        if not base_dir.is_absolute():
            base_dir = _AGENT_ROOT / "runs"

        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:18]
        suffix = uuid.uuid4().hex[:6]
        run_dir = base_dir / f"{ts}_{suffix}"

        (run_dir / "code").mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)

        config_raw = args.get("config_json")
        if config_raw:
            config_data = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
            (run_dir / "config.json").write_text(json.dumps(config_data, indent=2, ensure_ascii=False))

        signal_engine_code = args.get("signal_engine_py")
        if signal_engine_code:
            (run_dir / "code" / "signal_engine.py").write_text(_sanitize_signal_engine_code(signal_engine_code))

        return json.dumps(
            {
                "status": "ok",
                "run_dir": str(run_dir),
                "files_written": (
                    (["config.json"] if config_raw else [])
                    + (["code/signal_engine.py"] if signal_engine_code else [])
                ),
            }
        )
    except Exception as exc:
        logger.exception("setup_backtest_run tool error")
        return json.dumps({"status": "error", "error": str(exc)})


def _sanitize_signal_engine_code(source: str) -> str:
    """Normalize common invalid type-annotation patterns in generated code."""
    source = _decode_escaped_multiline_source(source)
    source = re.sub(
        r"from typing import ([^\n]+)",
        lambda m: _sanitize_typing_imports(m.group(1)),
        source,
    )
    if re.search(r"\b(?:Series|DataFrame)\b", source) and "import pandas as pd" not in source:
        source = "import pandas as pd\n" + source
    source = re.sub(r"(?<![\.\w])DataFrame\b", "pd.DataFrame", source)
    source = re.sub(r"(?<![\.\w])Series\b", "pd.Series", source)
    return source


def _decode_escaped_multiline_source(source: str) -> str:
    """Decode source accidentally passed as a single escaped string."""
    if "\\n" not in source:
        return source
    if "\n" in source and source.count("\n") > 2:
        return source
    try:
        decoded = bytes(source, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return source
    return decoded if "\n" in decoded else source


def _sanitize_typing_imports(imports: str) -> str:
    names = [part.strip() for part in imports.split(",")]
    filtered = [name for name in names if name not in {"Series", "DataFrame"}]
    if filtered:
        return f"from typing import {', '.join(filtered)}"
    return "import typing"


def _backtest(args: dict, **_) -> str:
    try:
        from src.tools.backtest_tool import run_backtest

        return run_backtest(run_dir=args["run_dir"])
    except Exception as exc:
        logger.exception("backtest tool error")
        return json.dumps({"status": "error", "error": str(exc)})


def _factor_analysis(args: dict, **_) -> str:
    try:
        from src.tools.factor_analysis_tool import run_factor_analysis

        return run_factor_analysis(
            factor_csv=args["factor_csv"],
            return_csv=args["return_csv"],
            output_dir=args["output_dir"],
            n_groups=args.get("n_groups", 5),
        )
    except Exception as exc:
        logger.exception("factor_analysis tool error")
        return json.dumps({"status": "error", "error": str(exc)})


def _options_pricing(args: dict, **_) -> str:
    try:
        from src.tools.options_pricing_tool import OptionsPricingTool

        tool = OptionsPricingTool()
        return tool.execute(**args)
    except Exception as exc:
        logger.exception("options_pricing tool error")
        return json.dumps({"status": "error", "error": str(exc)})


def _pattern(args: dict, **_) -> str:
    try:
        from src.tools.pattern_tool import run_pattern

        return run_pattern(
            run_dir=args["run_dir"],
            patterns=args.get("patterns", "all"),
            window=args.get("window", 10),
        )
    except Exception as exc:
        logger.exception("pattern tool error")
        return json.dumps({"status": "error", "error": str(exc)})


def _list_swarm_presets(args: dict, **_) -> str:
    try:
        from src.swarm.presets import list_presets
        return json.dumps(list_presets(), ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.exception("list_swarm_presets error")
        return json.dumps({"status": "error", "error": str(exc)})


def _run_swarm(args: dict, **_) -> str:
    import time
    try:
        from pathlib import Path
        from src.swarm.runtime import WorkflowRuntime
        from src.swarm.store import SwarmStore
        from src.swarm.models import RunStatus
        from src.swarm.presets import list_presets

        preset_name = args["preset_name"]
        variables = args.get("variables") or {}

        # Pre-flight: validate required variables before starting the run
        presets = {p["name"]: p for p in list_presets()}
        if preset_name not in presets:
            available = list(presets.keys())
            return json.dumps({
                "status": "error",
                "error": f"Unknown preset '{preset_name}'. Call list_swarm_presets to see available options.",
                "available_presets": available,
            }, ensure_ascii=False)

        missing = [
            v["name"] for v in presets[preset_name].get("variables", [])
            if v.get("required") and not variables.get(v["name"])
        ]
        if missing:
            required = [v for v in presets[preset_name].get("variables", []) if v.get("required")]
            return json.dumps({
                "status": "error",
                "error": f"Missing required variables for preset '{preset_name}': {missing}. Re-call run_swarm with all required variables filled in.",
                "required_variables": required,
                "provided_variables": variables,
            }, ensure_ascii=False)

        swarm_dir = Path(__file__).resolve().parents[2] / ".swarm" / "runs"
        store = SwarmStore(base_dir=swarm_dir)
        runtime = WorkflowRuntime(store=store)

        try:
            run = runtime.start_run(preset_name, variables)
        except FileNotFoundError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
        except ValueError as exc:
            return json.dumps({"status": "error", "error": f"DAG validation failed: {exc}"}, ensure_ascii=False)

        # Poll until complete (max 40 minutes — investment_committee has 3 serial
        # layers × 600s each = 1800s theoretical max; add buffer for startup overhead)
        for _ in range(480):
            time.sleep(5)
            current = store.load_run(run.id)
            if current is None:
                return json.dumps({"status": "error", "error": "Run record lost"}, ensure_ascii=False)
            if current.status in (RunStatus.completed, RunStatus.failed, RunStatus.cancelled):
                tasks = [
                    {"id": t.id, "agent_id": t.agent_id, "status": t.status.value, "summary": t.summary}
                    for t in current.tasks
                ]
                return json.dumps({
                    "status": current.status.value,
                    "preset": preset_name,
                    "run_id": current.id,
                    "final_report": current.final_report,
                    "tasks": tasks,
                    "total_input_tokens": current.total_input_tokens,
                    "total_output_tokens": current.total_output_tokens,
                }, ensure_ascii=False, indent=2)

        return json.dumps({"status": "error", "error": "Swarm timed out after 40 minutes"}, ensure_ascii=False)
    except Exception as exc:
        logger.exception("run_swarm error")
        return json.dumps({"status": "error", "error": str(exc)})



_SETUP_BACKTEST_RUN_SCHEMA = {
    "name": "setup_backtest_run",
    "description": (
        "Create a new backtest run directory (timestamped, under agent/runs/) and optionally "
        "write config.json and code/signal_engine.py in one step. "
        "Returns the run_dir path to pass to backtest(). "
        "ALWAYS call this before backtest() to get a valid run_dir. "
        "Workflow: setup_backtest_run(config_json=..., signal_engine_py=...) -> backtest(run_dir=...)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "config_json": {
                "type": "string",
                "description": (
                    "JSON string for config.json. Required fields: "
                    "source ('auto'|'tushare'|'yfinance'|'okx'), "
                    "codes (list of symbol strings), "
                    "start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), "
                    "initial_cash (number). "
                    "Optional: optimizer ('risk_parity'|'equal_weight'), "
                    "optimizer_params, commission, slippage."
                ),
            },
            "signal_engine_py": {
                "type": "string",
                "description": (
                    "Python source code for code/signal_engine.py. "
                    "Must define class SignalEngine with method "
                    "generate(data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]. "
                    "Import pandas as pd and use pandas-qualified annotations. "
                    "Signal series values are target weights in [-1, 1] (0 = flat). "
                    "If optimizer is set in config, return raw directional weights (1.0 = long); "
                    "the optimizer handles sizing."
                ),
            },
            "base_dir": {
                "type": "string",
                "description": "Optional override for the parent runs/ directory. Defaults to agent/runs/.",
            },
        },
        "required": [],
    },
}

_BACKTEST_SCHEMA = {
    "name": "backtest",
    "description": (
        "Run backtest: validates config.json + code/signal_engine.py in the run "
        "directory, then executes the built-in backtest engine. "
        "Returns exit code, stdout/stderr, and artifact paths."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "run_dir": {
                "type": "string",
                "description": "Path to the run directory containing config.json and code/signal_engine.py",
            },
        },
        "required": ["run_dir"],
    },
}

_FACTOR_ANALYSIS_SCHEMA = {
    "name": "factor_analysis",
    "description": (
        "Factor analysis: compute IC, IR, and layered NAV given a factor CSV and a "
        "returns CSV. Outputs ic_series.csv, ic_summary.json, and group_equity.csv."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "factor_csv": {
                "type": "string",
                "description": "Factor values CSV path (index=date, columns=asset codes)",
            },
            "return_csv": {
                "type": "string",
                "description": "Returns CSV path (same shape as factor_csv)",
            },
            "output_dir": {
                "type": "string",
                "description": "Directory to write analysis outputs",
            },
            "n_groups": {
                "type": "integer",
                "description": "Number of quantile groups for layered backtest (default 5)",
            },
        },
        "required": ["factor_csv", "return_csv", "output_dir"],
    },
}

_OPTIONS_PRICING_SCHEMA = {
    "name": "options_pricing",
    "description": (
        "Options pricing: compute theoretical price and Greeks (delta, gamma, theta, vega) "
        "using the Black-Scholes model for a European call or put option."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "spot": {"type": "number", "description": "Current underlying price"},
            "strike": {"type": "number", "description": "Strike price"},
            "expiry_days": {"type": "number", "description": "Days to expiry"},
            "volatility": {"type": "number", "description": "Annualised volatility (e.g. 0.20 = 20%)"},
            "option_type": {"type": "string", "enum": ["call", "put"], "description": "Option type"},
            "risk_free_rate": {"type": "number", "description": "Risk-free rate (default 0.05)"},
        },
        "required": ["spot", "strike", "expiry_days", "volatility", "option_type"],
    },
}

_PATTERN_SCHEMA = {
    "name": "pattern",
    "description": (
        "Chart pattern detection on OHLCV data stored in run_dir/artifacts/ohlcv_*.csv. "
        "Detects: peaks_valleys, candlestick, support_resistance, trend_slope, "
        "head_and_shoulders, double_top_bottom, triangle, broadening. "
        "Call after backtest when OHLCV artifacts are present."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "run_dir": {
                "type": "string",
                "description": "Path to the run directory (must contain artifacts/ohlcv_*.csv)",
            },
            "patterns": {
                "type": "string",
                "description": (
                    "Comma-separated pattern names or 'all'. "
                    "Options: peaks_valleys, candlestick, support_resistance, trend_slope, "
                    "head_and_shoulders, double_top_bottom, triangle, broadening"
                ),
            },
            "window": {
                "type": "integer",
                "description": "Detection window size (default 10)",
            },
        },
        "required": ["run_dir"],
    },
}

TOOLSET_NAME = "vibe_trading_finance"

_LIST_SWARM_PRESETS_SCHEMA = {
    "name": "list_swarm_presets",
    "description": (
        "List available swarm multi-agent team presets. "
        "Returns preset names, descriptions, agent counts, and required variables. "
        "Call this before run_swarm to see what presets exist and what variables they need."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

_RUN_SWARM_SCHEMA = {
    "name": "run_swarm",
    "description": (
        "Run a swarm multi-agent team and return the final report. "
        "Assembles a team of specialized agents that collaborate through a DAG workflow. "
        "For example, 'investment_committee' runs bull analyst, bear analyst, risk officer, "
        "and portfolio manager in sequence. Call list_swarm_presets first to see options. "
        "IMPORTANT: Always extract required variable values from the user message before calling — "
        "never pass an empty variables dict."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "preset_name": {
                "type": "string",
                "description": "Swarm preset name (e.g. 'investment_committee', 'quant_strategy_desk'). Use list_swarm_presets to see all options.",
            },
            "variables": {
                "type": "object",
                "description": "Required variables extracted from user context (e.g. {\"target\": \"NVDA\", \"market\": \"US\"}). Check list_swarm_presets for required keys.",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["preset_name", "variables"],
    },
}

TOOL_REGISTRATIONS = [
    {
        "name": "setup_backtest_run",
        "toolset": TOOLSET_NAME,
        "schema": _SETUP_BACKTEST_RUN_SCHEMA,
        "handler": _setup_backtest_run,
        "emoji": "🗂️",
        "description": _SETUP_BACKTEST_RUN_SCHEMA["description"],
    },
    {
        "name": "backtest",
        "toolset": TOOLSET_NAME,
        "schema": _BACKTEST_SCHEMA,
        "handler": _backtest,
        "emoji": "📈",
        "description": _BACKTEST_SCHEMA["description"],
    },
    {
        "name": "factor_analysis",
        "toolset": TOOLSET_NAME,
        "schema": _FACTOR_ANALYSIS_SCHEMA,
        "handler": _factor_analysis,
        "emoji": "📊",
        "description": _FACTOR_ANALYSIS_SCHEMA["description"],
    },
    {
        "name": "options_pricing",
        "toolset": TOOLSET_NAME,
        "schema": _OPTIONS_PRICING_SCHEMA,
        "handler": _options_pricing,
        "emoji": "📉",
        "description": _OPTIONS_PRICING_SCHEMA["description"],
    },
    {
        "name": "pattern",
        "toolset": TOOLSET_NAME,
        "schema": _PATTERN_SCHEMA,
        "handler": _pattern,
        "emoji": "🕯️",
        "description": _PATTERN_SCHEMA["description"],
    },
    {
        "name": "list_swarm_presets",
        "toolset": TOOLSET_NAME,
        "schema": _LIST_SWARM_PRESETS_SCHEMA,
        "handler": _list_swarm_presets,
        "emoji": "🐝",
        "description": _LIST_SWARM_PRESETS_SCHEMA["description"],
    },
    {
        "name": "run_swarm",
        "toolset": TOOLSET_NAME,
        "schema": _RUN_SWARM_SCHEMA,
        "handler": _run_swarm,
        "emoji": "🐝",
        "description": _RUN_SWARM_SCHEMA["description"],
    },
]

