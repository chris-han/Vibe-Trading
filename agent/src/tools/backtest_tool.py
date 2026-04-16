"""Backtest execution tool: validates config.json + signal_engine.py and runs the built-in engine."""

from __future__ import annotations

import json
from pathlib import Path

from .base import BaseTool
from src.backtest.bootstrap import bootstrap_run_from_prompt
from src.core.runner import Runner


def _resolve_prepared_run_dir(run_path: Path) -> tuple[Path, str | None]:
    """Resolve a nested prepared run dir when callers pass the parent folder by mistake."""
    config_path = run_path / "config.json"
    signal_path = run_path / "code" / "signal_engine.py"
    if config_path.exists() or signal_path.exists():
        return run_path, None

    prepared_children: list[Path] = []
    for child in sorted(run_path.iterdir()) if run_path.exists() else []:
        if not child.is_dir():
            continue
        child_config = child / "config.json"
        child_signal = child / "code" / "signal_engine.py"
        if child_config.exists() or child_signal.exists():
            prepared_children.append(child)

    if len(prepared_children) == 1:
        resolved = prepared_children[0]
        detail = f"resolved nested prepared run_dir: {resolved}"
        return resolved, detail

    return run_path, None


def run_backtest(run_dir: str) -> str:
    """Run backtest: validate config.json + signal_engine.py, invoke built-in engine.

    Args:
        run_dir: Path to the run directory.

    Returns:
        JSON-formatted execution result.
    """
    run_path, resolution_detail = _resolve_prepared_run_dir(Path(run_dir))
    req_path = run_path / "req.json"

    config_path = run_path / "config.json"
    signal_path = run_path / "code" / "signal_engine.py"

    bootstrap_result = None
    if req_path.exists() and (not config_path.exists() or not signal_path.exists()):
        try:
            req_payload = json.loads(req_path.read_text(encoding="utf-8"))
            prompt = str(req_payload.get("prompt") or "").strip()
            if prompt:
                bootstrap_result = bootstrap_run_from_prompt(run_path, prompt)
        except Exception:
            pass

    if not config_path.exists():
        if bootstrap_result and bootstrap_result.get("status") == "skipped":
            detail = bootstrap_result.get("detail") or {}
            message = detail.get("message")
            reason = bootstrap_result.get("reason") or "bootstrap_skipped"
            return json.dumps({
                "status": "error",
                "error": message or "Unable to derive a runnable backtest config from the prompt.",
                "reason": reason,
                "detail": detail,
                "hint": (
                    "Provide explicit symbols/codes, or use a prompt whose target universe can be "
                    "resolved by the configured data source."
                ),
                "run_dir": run_dir,
            }, ensure_ascii=False)
        return json.dumps({
            "status": "error",
            "error": "config.json not found",
            "hint": (
                "Create the run with setup_backtest_run(config_json=..., signal_engine_py=...) "
                "before calling backtest(run_dir=...)."
            ),
            "run_dir": run_dir,
        }, ensure_ascii=False)

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return json.dumps({"status": "error", "error": f"config.json parse error: {e}"}, ensure_ascii=False)

    if not isinstance(config, dict):
        return json.dumps({"status": "error", "error": f"config.json must be a JSON object, got {type(config).__name__}"}, ensure_ascii=False)

    if "source" not in config:
        return json.dumps({"status": "error", "error": "config.json missing 'source' field (tushare/okx/yfinance)"}, ensure_ascii=False)

    valid_sources = {"tushare", "okx", "yfinance", "auto"}
    if config["source"] not in valid_sources:
        return json.dumps({"status": "error", "error": f"source must be one of {valid_sources}, got: {config['source']}"}, ensure_ascii=False)

    if not signal_path.exists():
        return json.dumps({
            "status": "error",
            "error": "code/signal_engine.py not found",
            "hint": (
                "Create the run with setup_backtest_run(config_json=..., signal_engine_py=...) "
                "before calling backtest(run_dir=...)."
            ),
            "run_dir": run_dir,
        }, ensure_ascii=False)

    agent_root = Path(__file__).resolve().parents[2]
    entry_script = agent_root / "backtest" / "runner.py"

    runner = Runner(timeout=300)
    result = runner.execute(
        entry_script,
        run_path,
        cwd=agent_root,
        cli_args=[str(run_path)],
    )

    artifacts_found = {name: str(path) for name, path in result.artifacts.items()}
    return json.dumps({
        "status": "ok" if result.success else "error",
        "exit_code": result.exit_code,
        "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
        "stderr": result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
        "artifacts": artifacts_found,
        "run_dir": run_dir,
        **({"resolved_run_dir": str(run_path), "detail": resolution_detail} if resolution_detail else {}),
    }, ensure_ascii=False)


class BacktestTool(BaseTool):
    """Backtest execution tool."""

    name = "backtest"
    description = "Run backtest: validate config.json + signal_engine.py, invoke built-in engine."
    parameters = {
        "type": "object",
        "properties": {
            "run_dir": {"type": "string", "description": "Path to the run directory"},
        },
        "required": ["run_dir"],
    }
    repeatable = True

    def execute(self, **kwargs) -> str:
        """Execute backtest."""
        return run_backtest(kwargs["run_dir"])
