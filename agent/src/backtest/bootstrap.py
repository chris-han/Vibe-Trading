"""Backtest run bootstrap helpers.

Creates a minimal valid ``config.json`` and ``code/signal_engine.py`` from a
natural-language prompt so the run directory is executable before the agent
iterates on strategy details.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_BACKTEST_TERMS = ("backtest", "strategy", "portfolio", "signal", "optimizer")
_US_TICKER_STOPWORDS = {
    "MACD", "RSI", "SMA", "EMA", "ATR", "ROC", "ADX", "CCI", "MFI", "OBV",
    "BTC", "ETH", "USDT", "LONG", "SHORT", "OOS", "CSI", "USD", "HKD",
    "SZ", "SH", "BJ", "HK", "US",
    # Common quant terms and China index-futures symbols that should never
    # be auto-promoted to ``.US`` tickers from natural-language prompts.
    "IC", "IR", "ICIR", "NAV", "PNL", "IF", "IH", "IM",
}
_CHINA_MARKET_HINTS = (
    "csi 300",
    "csi300",
    "csi 500",
    "csi500",
    "csi 1000",
    "csi1000",
    "a-share",
    "ashare",
    "china a",
    "沪深",
    "中证",
    "成分股",
    "constituents",
)
_NAMED_UNIVERSES = (
    (re.compile(r"\b(?:csi\s*300|hs300|沪深300)\b", re.IGNORECASE), "399300.SZ", "CSI 300"),
    (re.compile(r"\b(?:csi\s*500|中证500)\b", re.IGNORECASE), "000905.SH", "CSI 500"),
    (re.compile(r"\b(?:csi\s*1000|中证1000)\b", re.IGNORECASE), "000852.SH", "CSI 1000"),
    (re.compile(r"\b(?:sse\s*50|上证50)\b", re.IGNORECASE), "000016.SH", "SSE 50"),
)


def is_backtest_prompt(prompt: str) -> bool:
    text = (prompt or "").lower()
    return any(term in text for term in _BACKTEST_TERMS)


def _normalize_a_share(code: str) -> str:
    if "." in code:
        return code.upper()
    return f"{code}.SH" if code.startswith(("600", "601", "603")) else f"{code}.SZ"


def extract_codes(prompt: str) -> list[str]:
    text = prompt or ""
    codes: list[str] = []
    lowered = text.lower()

    patterns = [
        r"\b\d{6}\.(?:SZ|SH|BJ)\b",
        r"\b\d{3,5}\.HK\b",
        r"\b[A-Z]{1,6}\.US\b",
        r"\b[A-Z]{2,10}-USDT\b",
        r"\b[A-Z]{2,10}/USDT\b",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            code = match.upper().replace("/", "-")
            if code not in codes:
                codes.append(code)

    for match in re.findall(r"\b\d{6}\b", text):
        code = _normalize_a_share(match)
        if code not in codes:
            codes.append(code)

    masked_text = re.sub(r"\b(?:\d{6}\.(?:SZ|SH|BJ)|\d{3,5}\.HK|[A-Z]{1,6}\.US|[A-Z]{2,10}-USDT|[A-Z]{2,10}/USDT)\b", " ", text)
    allow_bare_us_ticker_inference = not any(hint in lowered for hint in _CHINA_MARKET_HINTS)
    if allow_bare_us_ticker_inference:
        for match in re.findall(r"\b[A-Z]{1,5}\b", masked_text):
            upper = match.upper()
            if upper in _US_TICKER_STOPWORDS:
                continue
            if any(upper == existing.split(".")[0] for existing in codes if "." in existing):
                continue
            if any(upper == existing.split("-")[0] for existing in codes if "-" in existing):
                continue
            codes.append(f"{upper}.US")

    return codes


def extract_date_range(prompt: str, today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    text = prompt or ""

    explicit_matches = list(re.finditer(r"\b(20\d{2})[-/](\d{2})[-/](\d{2})\b", text))
    if len(explicit_matches) >= 2:
        first = explicit_matches[0].group(0).replace("/", "-")
        second = explicit_matches[1].group(0).replace("/", "-")
        return first, second

    year_span = re.search(r"\bfrom\s+(20\d{2})\s+to\s+(20\d{2})\b", text, flags=re.IGNORECASE)
    if year_span:
        start_year, end_year = year_span.groups()
        return f"{start_year}-01-01", f"{end_year}-12-31"

    full_year = re.search(r"\b(?:full[- ]year|calendar year|entire year)\s+(20\d{2})\b", text, flags=re.IGNORECASE)
    if full_year:
        year = full_year.group(1)
        return f"{year}-01-01", f"{year}-12-31"

    bare_year = re.search(r"\bfor\s+(20\d{2})\b", text, flags=re.IGNORECASE)
    if bare_year:
        year = bare_year.group(1)
        return f"{year}-01-01", f"{year}-12-31"

    rel = re.search(r"\blast\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)\b", text, flags=re.IGNORECASE)
    if rel:
        count = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("day"):
            start = today - timedelta(days=count)
        elif unit.startswith("week"):
            start = today - timedelta(weeks=count)
        elif unit.startswith("month"):
            start = today - timedelta(days=count * 30)
        else:
            start = today - timedelta(days=count * 365)
        return start.isoformat(), today.isoformat()

    default_start = date(today.year - 10, today.month, today.day)
    return default_start.isoformat(), today.isoformat()


def extract_optimizer(prompt: str) -> str | None:
    text = re.sub(r"[-_]+", " ", (prompt or "").lower())
    mapping = {
        "risk parity": "risk_parity",
        "equal volatility": "equal_volatility",
        "mean variance": "mean_variance",
        "max diversification": "max_diversification",
        "max sharpe": "mean_variance",
    }
    for phrase, optimizer in mapping.items():
        if phrase in text:
            return optimizer
    return None


def _month_bounds(anchor: date) -> tuple[str, str]:
    month_start = anchor.replace(day=1)
    if anchor.month == 12:
        next_month = anchor.replace(year=anchor.year + 1, month=1, day=1)
    else:
        next_month = anchor.replace(month=anchor.month + 1, day=1)
    month_end = next_month - timedelta(days=1)
    return month_start.strftime("%Y%m%d"), month_end.strftime("%Y%m%d")


def _resolve_named_universe(prompt: str, end_date: str) -> dict[str, Any] | None:
    text = prompt or ""
    matched = None
    for pattern, index_code, label in _NAMED_UNIVERSES:
        if pattern.search(text):
            matched = {"index_code": index_code, "label": label}
            break
    if matched is None:
        return None

    try:
        from runtime_env import ensure_runtime_env
    except ImportError:
        ensure_runtime_env = None  # type: ignore

    if ensure_runtime_env is not None:
        ensure_runtime_env()

    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        return {
            "status": "error",
            "reason": "tushare_token_missing",
            "message": f"{matched['label']} constituents require Tushare with TUSHARE_TOKEN configured.",
            **matched,
        }

    try:
        import pandas as pd
        import tushare as ts
    except ImportError as exc:
        return {
            "status": "error",
            "reason": "tushare_unavailable",
            "message": f"Tushare import failed while resolving {matched['label']} constituents: {exc}",
            **matched,
        }

    api = ts.pro_api(token)
    anchor = pd.to_datetime(end_date).date()

    # index_weight is monthly. Search backward a few months to find the latest
    # available constituent snapshot near the requested backtest end date.
    for offset in range(6):
        probe_month = anchor - timedelta(days=offset * 31)
        start, end = _month_bounds(probe_month)
        try:
            df = api.index_weight(index_code=matched["index_code"], start_date=start, end_date=end)
        except Exception as exc:
            return {
                "status": "error",
                "reason": "tushare_index_weight_failed",
                "message": f"Failed to resolve {matched['label']} constituents via Tushare index_weight: {exc}",
                **matched,
            }
        if df is None or df.empty:
            continue
        if "con_code" not in df.columns:
            break
        codes = sorted({str(code).upper() for code in df["con_code"].dropna().tolist() if str(code).strip()})
        if codes:
            return {
                "status": "ok",
                "source": "tushare",
                "codes": codes,
                **matched,
            }

    return {
        "status": "error",
        "reason": "universe_constituents_unavailable",
        "message": f"No constituent data returned for {matched['label']} near {end_date}.",
        **matched,
    }


def build_bootstrap_config(prompt: str, today: date | None = None) -> dict[str, Any] | None:
    codes = extract_codes(prompt)

    start_date, end_date = extract_date_range(prompt, today=today)
    source = "auto"

    if not codes:
        universe = _resolve_named_universe(prompt, end_date)
        if universe is None:
            return None
        if universe.get("status") != "ok":
            return {
                "__bootstrap_error__": universe,
            }
        codes = universe["codes"]
        source = str(universe.get("source") or "tushare")

    if all(code.endswith((".SZ", ".SH", ".BJ")) for code in codes):
        source = "tushare"

    optimizer = extract_optimizer(prompt)
    config: dict[str, Any] = {
        "source": source,
        "codes": codes,
        "start_date": start_date,
        "end_date": end_date,
        "interval": "1D",
        "initial_cash": 1_000_000,
        "commission": 0.001,
        "extra_fields": None,
        "optimizer": optimizer,
        "optimizer_params": {"lookback": 60} if optimizer in {"risk_parity", "equal_volatility"} else {},
        "engine": "daily",
    }
    return config


def build_bootstrap_signal_engine(config: dict[str, Any]) -> str:
    optimizer = config.get("optimizer")
    use_optimizer = bool(optimizer)
    weight_expr = "1.0" if use_optimizer else "1.0 / len(codes)"
    return f'''from typing import Dict

import pandas as pd


class SignalEngine:
    """Bootstrap signal engine.

    Seeds the run with a simple always-invested allocation so the backtest can
    execute before the agent refines the strategy logic.
    """

    def generate(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]:
        if not data_map:
            return {{}}

        codes = list(data_map.keys())
        target_weight = {weight_expr}
        result: Dict[str, pd.Series] = {{}}
        for code, df in data_map.items():
            result[code] = pd.Series(target_weight, index=df.index, dtype=float)
        return result
'''


def bootstrap_run_from_prompt(
    run_dir: Path,
    prompt: str,
    *,
    overwrite: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "code").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    req_path = run_dir / "req.json"
    if overwrite or not req_path.exists():
        req_path.write_text(
            json.dumps({"prompt": prompt, "context": {}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    config = build_bootstrap_config(prompt, today=today)
    if config is None:
        return {"status": "skipped", "reason": "no_codes"}
    if "__bootstrap_error__" in config:
        return {
            "status": "skipped",
            "reason": "universe_resolution_failed",
            "detail": config["__bootstrap_error__"],
        }

    config_path = run_dir / "config.json"
    signal_path = run_dir / "code" / "signal_engine.py"

    files_written: list[str] = []
    if overwrite or not config_path.exists():
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        files_written.append("config.json")

    if overwrite or not signal_path.exists():
        signal_path.write_text(build_bootstrap_signal_engine(config), encoding="utf-8")
        files_written.append("code/signal_engine.py")

    return {
        "status": "ok",
        "config": config,
        "files_written": files_written,
    }
