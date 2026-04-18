"""Fixed backtest entrypoint: read config.json, select loader by source, import signal_engine, run engine.

Supports ``source="auto"`` to route codes to loaders by symbol format.
Supports ``interval`` for bar size (1m/5m/15m/30m/1H/4H/1D, default 1D).
Supports ``engine`` for backtest engine (daily/options, default daily).

Usage: ``python -m backtest.runner <run_dir>``
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List


def _sanitize_signal_engine_source(source: str) -> str:
    """Repair common LLM-generated typing mistakes in signal engine code.

    Generated strategies sometimes use ``from typing import ... Series, DataFrame``,
    which is invalid in Python 3.12+, and may also reference bare ``Series`` /
    ``DataFrame`` annotations. Normalize those cases to pandas-qualified types.

    Args:
        source: Raw Python source code.

    Returns:
        Sanitized Python source code.
    """
    source = _decode_escaped_multiline_source(source)
    source = re.sub(
        r"from typing import ([^\n]+)",
        lambda m: _sanitize_typing_import_line(m.group(1)),
        source,
    )

    if re.search(r"\b(?:Series|DataFrame)\b", source) and "import pandas as pd" not in source:
        source = "import pandas as pd\n" + source

    source = re.sub(r"(?<![\.\w])DataFrame\b", "pd.DataFrame", source)
    source = re.sub(r"(?<![\.\w])Series\b", "pd.Series", source)
    return source


def _decode_escaped_multiline_source(source: str) -> str:
    """Decode source accidentally written with literal escape sequences."""
    if "\\n" not in source:
        return source
    if "\n" in source and source.count("\n") > 2:
        return source
    try:
        decoded = bytes(source, "utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return source
    return decoded if "\n" in decoded else source


def _sanitize_typing_import_line(imports: str) -> str:
    names = [part.strip() for part in imports.split(",")]
    filtered = [name for name in names if name not in {"Series", "DataFrame"}]
    if filtered:
        return f"from typing import {', '.join(filtered)}"
    return "import typing"


def _load_module_from_file(file_path: Path, module_name: str):
    """Load a Python module from a file path.

    Args:
        file_path: Path to the ``.py`` file.
        module_name: Logical module name.

    Returns:
        Loaded module object.
    """
    import types

    source = file_path.read_text(encoding="utf-8")
    if file_path.name == "signal_engine.py":
        source = _sanitize_signal_engine_source(source)

    module = types.ModuleType(module_name)
    module.__file__ = str(file_path)
    sys.modules[module_name] = module
    exec(compile(source, str(file_path), "exec"), module.__dict__)
    return module


# --- Market detection ---

_PATTERNS = [
    (re.compile(r"^\d{6}\.(SZ|SH|BJ)$", re.I), "tushare"),
    (re.compile(r"^[A-Z]+\.US$", re.I), "yfinance"),
    (re.compile(r"^\d{3,5}\.HK$", re.I), "yfinance"),
    (re.compile(r"^[A-Z]+-USDT$", re.I), "okx"),
    # Crypto pairs on yfinance (e.g. BTC-USD, ETH-USD)
    (re.compile(r"^[A-Z]+-USD$", re.I), "yfinance"),
    # Bare US-style tickers (1-5 uppercase letters, no dots/dashes)
    (re.compile(r"^[A-Z]{1,5}$"), "yfinance"),
]


def _detect_source(code: str) -> str:
    """Infer data source from symbol format.

    Args:
        code: Ticker / symbol string.

    Returns:
        Source name (tushare/okx/yfinance); unknown defaults to ``tushare``.
    """
    for pattern, source in _PATTERNS:
        if pattern.match(code):
            return source
    return "tushare"


def _group_codes_by_source(codes: List[str]) -> Dict[str, List[str]]:
    """Group symbols by inferred source.

    Args:
        codes: List of symbol strings.

    Returns:
        Mapping source -> list of codes.
    """
    groups: Dict[str, List[str]] = {}
    for code in codes:
        src = _detect_source(code)
        groups.setdefault(src, []).append(code)
    return groups


def _get_loader(source: str):
    """Return the DataLoader class for a source name.

    Args:
        source: Source name.

    Returns:
        DataLoader class.
    """
    if source == "okx":
        from backtest.loaders.okx import DataLoader
    elif source == "yfinance":
        from backtest.loaders.yfinance_loader import DataLoader
    elif source == "tushare":
        from backtest.loaders.tushare import DataLoader
    else:
        from backtest.loaders.tushare import DataLoader
    return DataLoader


def _normalize_codes(codes: List[str], source: str) -> List[str]:
    """Normalize symbol strings for a source.

    Args:
        codes: Raw code list.
        source: Data source.

    Returns:
        Normalized codes.
    """
    if source == "okx":
        return [c.replace("/", "-").upper() for c in codes]
    return codes


# --- Main entry ---

def main(run_dir: Path) -> None:
    """Load config, fetch data, run the selected backtest engine.

    With ``source="auto"``, routes each code through the appropriate loader.

    Args:
        run_dir: Run directory containing ``config.json`` and ``code/signal_engine.py``.
    """
    config_path = run_dir / "config.json"
    if not config_path.exists():
        print(json.dumps({"error": "config.json not found"}))
        sys.exit(1)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    source = config.get("source", "tushare")
    codes = config.get("codes", [])

    # Load signal engine
    signal_path = run_dir / "code" / "signal_engine.py"
    if not signal_path.exists():
        print(json.dumps({"error": "code/signal_engine.py not found"}))
        sys.exit(1)

    signal_module = _load_module_from_file(signal_path, "signal_engine")
    engine_cls = getattr(signal_module, "SignalEngine", None)
    if engine_cls is None:
        print(json.dumps({"error": "SignalEngine class not found in signal_engine.py"}))
        sys.exit(1)

    # Data: auto split vs single loader
    interval = config.get("interval", "1D")

    if source == "auto":
        data_map = _fetch_auto(codes, config, interval)
    else:
        codes = _normalize_codes(codes, source)
        config["codes"] = codes
        LoaderCls = _get_loader(source)
        loader = LoaderCls()
        data_map = loader.fetch(
            codes,
            config.get("start_date", ""),
            config.get("end_date", ""),
            fields=config.get("extra_fields") or None,
            interval=interval,
        )
    if not data_map:
        print(json.dumps({"error": "No data fetched"}))
        sys.exit(1)

    # Engine
    engine_type = config.get("engine", "daily")
    import inspect
    sig = inspect.signature(engine_cls.__init__)
    # Pass config if the constructor accepts it (beyond 'self')
    params = list(sig.parameters.keys())
    if len(params) > 1 and params[1] == "config":
        signal_engine = engine_cls(config)
    else:
        try:
            signal_engine = engine_cls()
        except TypeError:
            signal_engine = engine_cls(config)

    # Annualization bars
    effective_source = _detect_primary_source(codes, source)
    from backtest.metrics import calc_bars_per_year
    bars_per_year = calc_bars_per_year(interval, effective_source)

    # Auto mode: wrap preloaded data in a dummy loader
    if source == "auto":
        loader = _AutoLoader(data_map)

    if engine_type == "options":
        from backtest.engines.options_portfolio import run_options_backtest
        run_options_backtest(config, loader, signal_engine, run_dir, bars_per_year=bars_per_year)
    else:
        market_engine = _create_market_engine(effective_source, config, codes)
        market_engine.run_backtest(config, loader, signal_engine, run_dir, bars_per_year=bars_per_year)


def _create_market_engine(source: str, config: dict, codes: List[str]):
    """Create the appropriate market engine based on data source.

    Args:
        source: Data source (okx / tushare / yfinance).
        config: Backtest configuration.
        codes: Instrument codes.

    Returns:
        BaseEngine subclass instance.
    """
    if source == "okx":
        from backtest.engines.crypto import CryptoEngine
        return CryptoEngine(config)
    elif source == "tushare":
        from backtest.engines.china_a import ChinaAEngine
        return ChinaAEngine(config)
    elif source == "yfinance":
        from backtest.engines.global_equity import GlobalEquityEngine
        market = _detect_submarket(codes)
        return GlobalEquityEngine(config, market=market)
    else:
        # Default: crypto (most permissive rules)
        from backtest.engines.crypto import CryptoEngine
        return CryptoEngine(config)


def _detect_submarket(codes: List[str]) -> str:
    """Detect US vs HK from symbol suffixes.

    Args:
        codes: Instrument codes.

    Returns:
        "hk" if any code ends with .HK, else "us".
    """
    for code in codes:
        if code.upper().endswith(".HK"):
            return "hk"
    return "us"


def _detect_primary_source(codes: List[str], source: str) -> str:
    """Pick primary source for annualization (e.g. bars per year).

    Args:
        codes: All symbols.
        source: Config ``source`` field.

    Returns:
        Dominant source name.
    """
    if source != "auto":
        return source
    groups = _group_codes_by_source(codes)
    if len(groups) == 1:
        return list(groups.keys())[0]
    # Mixed: use the source with the most symbols
    return max(groups, key=lambda s: len(groups[s]))


def _fetch_auto(codes: List[str], config: dict, interval: str = "1D") -> dict:
    """Auto mode: fetch per source and merge into one data map.

    Args:
        codes: All symbols.
        config: Backtest config dict.
        interval: Bar interval string.

    Returns:
        Merged ``code -> DataFrame`` map.
    """
    groups = _group_codes_by_source(codes)
    merged = {}
    start_date = config.get("start_date", "")
    end_date = config.get("end_date", "")

    for src, src_codes in groups.items():
        src_codes = _normalize_codes(src_codes, src)
        LoaderCls = _get_loader(src)
        loader = LoaderCls()
        # Only tushare supports extra_fields
        fields = config.get("extra_fields") if src == "tushare" else None
        result = loader.fetch(src_codes, start_date, end_date, fields=fields, interval=interval)
        merged.update(result)

    return merged


class _AutoLoader:
    """Dummy loader for auto mode: returns pre-fetched data maps."""

    def __init__(self, data_map: dict):
        self._data = data_map

    def fetch(self, codes, start_date, end_date, fields=None, interval="1D"):
        """Return preloaded rows for requested codes."""
        return {c: df for c, df in self._data.items() if c in codes}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python -m backtest.runner <run_dir>")
        sys.exit(1)
    main(Path(sys.argv[1]))
