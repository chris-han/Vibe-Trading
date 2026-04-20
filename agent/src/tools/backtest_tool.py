"""Backtest execution tool: validates config.json + signal_engine.py and runs the built-in engine."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from .base import BaseTool
from src.backtest.bootstrap import bootstrap_run_from_prompt
from src.core.runner import Runner


_NETWORK_ERROR_PATTERNS = (
    re.compile(r"HTTPSConnectionPool", re.I),
    re.compile(r"ConnectTimeout", re.I),
    re.compile(r"ReadTimeout", re.I),
    re.compile(r"timed out", re.I),
    re.compile(r"Temporary failure in name resolution", re.I),
    re.compile(r"Name or service not known", re.I),
    re.compile(r"Network is unreachable", re.I),
    re.compile(r"No route to host", re.I),
    re.compile(r"ProxyError", re.I),
    re.compile(r"SSLError", re.I),
)


def _validate_proxy_env_urls() -> None:
    """Fail fast with a clear error when proxy env vars contain malformed URLs."""
    for key in (
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
    ):
        value = str(os.environ.get(key) or "").strip()
        if not value:
            continue
        try:
            parsed = urlparse(value)
            if parsed.scheme:
                _ = parsed.port
        except ValueError as exc:
            raise RuntimeError(
                f"Malformed proxy environment variable {key}={value!r}. "
                "Fix or unset your proxy settings and try again."
            ) from exc


def _proxy_env_presence() -> dict[str, bool]:
    """Return a redacted proxy-env summary for diagnostics."""
    return {
        key: bool(str(os.environ.get(key) or "").strip())
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
    }


def _build_network_failure_detail(stdout: str, stderr: str) -> dict[str, object] | None:
    """Classify market-data fetch failures caused by network or proxy issues."""
    combined = "\n".join(part for part in (stdout, stderr) if part)
    if "No data fetched" not in combined:
        return None

    indicators = [pattern.pattern for pattern in _NETWORK_ERROR_PATTERNS if pattern.search(combined)]
    if not indicators:
        return None

    providers: list[str] = []
    if re.search(r"yfinance", combined, re.I):
        providers.append("yfinance")
    if re.search(r"OKX|okx", combined, re.I):
        providers.append("okx")

    return {
        "reason": "market_data_network_error",
        "diagnosis": (
            "Outbound market-data requests failed before the backtest could start. "
            "In ECS this usually means missing internet egress, blocked TCP/443, or missing/malformed proxy settings."
        ),
        "hint": (
            "Verify the ECS task can reach public HTTPS endpoints from inside the container. "
            "If the task runs in a private subnet, add a NAT gateway or explicit egress proxy. "
            "If your environment requires a proxy, set valid HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY values in the task definition."
        ),
        "detail": {
            "providers": providers,
            "proxy_env": _proxy_env_presence(),
            "network_indicators": indicators,
        },
    }


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
    try:
        _validate_proxy_env_urls()
    except RuntimeError as exc:
        return json.dumps({
            "status": "error",
            "error": str(exc),
            "reason": "invalid_proxy_env",
            "hint": "Fix or unset the proxy variables in the ECS task definition and redeploy.",
            "detail": {"proxy_env": _proxy_env_presence()},
            "run_dir": run_dir,
        }, ensure_ascii=False)

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
    payload = {
        "status": "ok" if result.success else "error",
        "exit_code": result.exit_code,
        "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
        "stderr": result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
        "artifacts": artifacts_found,
        "run_dir": run_dir,
        **({"resolved_run_dir": str(run_path), "detail": resolution_detail} if resolution_detail else {}),
    }

    if not result.success:
        network_failure = _build_network_failure_detail(result.stdout, result.stderr)
        if network_failure:
            payload.update(network_failure)

    return json.dumps(payload, ensure_ascii=False)


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
