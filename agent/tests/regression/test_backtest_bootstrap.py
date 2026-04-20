from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

HERMES_BACKEND = Path(__file__).resolve().parents[2]
_s = str(HERMES_BACKEND)
if _s not in sys.path:
    sys.path.insert(0, _s)


def test_bootstrap_run_from_prompt_generates_config_and_signal(tmp_path):
    from src.backtest.bootstrap import bootstrap_run_from_prompt

    result = bootstrap_run_from_prompt(
        tmp_path,
        "Backtest a risk-parity portfolio of 000001.SZ, BTC-USDT, and AAPL for full-year 2024",
    )

    assert result["status"] == "ok"

    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["codes"] == ["000001.SZ", "BTC-USDT", "AAPL.US"]
    assert config["start_date"] == "2024-01-01"
    assert config["end_date"] == "2024-12-31"
    assert config["optimizer"] == "risk_parity"
    signal_path = tmp_path / "code" / "signal_engine.py"
    assert signal_path.exists()
    signal_source = signal_path.read_text(encoding="utf-8")
    assert "Dict[str, pd.DataFrame]" in signal_source
    assert "Dict[str, pd.Series]" in signal_source
    assert "from typing import Dict, Series, DataFrame" not in signal_source


def test_run_backtest_bootstraps_from_req_when_config_missing(tmp_path):
    from src.tools.backtest_tool import run_backtest

    (tmp_path / "code").mkdir(parents=True, exist_ok=True)
    (tmp_path / "req.json").write_text(
        json.dumps({
            "prompt": "Backtest AAPL and MSFT for full-year 2024",
            "context": {},
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with patch("src.tools.backtest_tool.Runner") as MockRunner:
        runner = MockRunner.return_value
        runner.execute.return_value = MagicMock(
            success=True,
            exit_code=0,
            stdout="ok",
            stderr="",
            artifacts={},
        )
        raw = run_backtest(str(tmp_path))

    payload = json.loads(raw)
    assert payload["status"] == "ok"
    assert (tmp_path / "config.json").exists()
    assert (tmp_path / "code" / "signal_engine.py").exists()


def test_extract_codes_does_not_infer_ic_us_from_china_factor_prompt():
    from src.backtest.bootstrap import extract_codes

    prompt = (
        "Build a multi-factor alpha model using momentum, reversal, volatility, "
        "and turnover on CSI 300 constituents with IC-weighted factor synthesis, "
        "backtest 2023-2024"
    )

    assert extract_codes(prompt) == []


def test_build_bootstrap_config_resolves_named_universe(monkeypatch):
    from src.backtest import bootstrap

    monkeypatch.setattr(
        bootstrap,
        "_resolve_named_universe",
        lambda prompt, end_date: {
            "status": "ok",
            "source": "tushare",
            "codes": ["000001.SZ", "600000.SH"],
            "index_code": "399300.SZ",
            "label": "CSI 300",
        },
    )

    config = bootstrap.build_bootstrap_config(
        "Backtest CSI 300 constituents with momentum for full-year 2024"
    )

    assert config is not None
    assert config["source"] == "tushare"
    assert config["codes"] == ["000001.SZ", "600000.SH"]
    assert config["start_date"] == "2024-01-01"
    assert config["end_date"] == "2024-12-31"


def test_run_backtest_surfaces_universe_resolution_error(tmp_path):
    from src.tools.backtest_tool import run_backtest

    (tmp_path / "req.json").write_text(
        json.dumps({
            "prompt": "Backtest CSI 300 constituents with momentum for full-year 2024",
            "context": {},
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with patch("src.tools.backtest_tool.bootstrap_run_from_prompt") as mock_bootstrap:
        mock_bootstrap.return_value = {
            "status": "skipped",
            "reason": "universe_resolution_failed",
            "detail": {
                "reason": "tushare_index_weight_failed",
                "message": "Failed to resolve CSI 300 constituents via Tushare index_weight: permission denied",
            },
        }
        raw = run_backtest(str(tmp_path))

    payload = json.loads(raw)
    assert payload["status"] == "error"
    assert payload["reason"] == "universe_resolution_failed"
    assert "Failed to resolve CSI 300 constituents" in payload["error"]


def test_run_backtest_resolves_single_nested_prepared_run_dir(tmp_path):
    from src.tools.backtest_tool import run_backtest

    nested_run = tmp_path / "20260410_121400_01_abcd12"
    (nested_run / "code").mkdir(parents=True, exist_ok=True)
    (nested_run / "config.json").write_text(
        json.dumps(
            {
                "source": "yfinance",
                "codes": ["AAPL.US"],
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "initial_cash": 100000,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (nested_run / "code" / "signal_engine.py").write_text(
        "class SignalEngine:\n    def generate(self, data_map):\n        return {}\n",
        encoding="utf-8",
    )

    with patch("src.tools.backtest_tool.Runner") as MockRunner:
        runner = MockRunner.return_value
        runner.execute.return_value = MagicMock(
            success=True,
            exit_code=0,
            stdout="ok",
            stderr="",
            artifacts={},
        )
        raw = run_backtest(str(tmp_path))

    payload = json.loads(raw)
    assert payload["status"] == "ok"
    assert payload["run_dir"] == str(tmp_path)
    assert payload["resolved_run_dir"] == str(nested_run)


def test_run_backtest_rejects_malformed_proxy_env(tmp_path, monkeypatch):
    from src.tools.backtest_tool import run_backtest

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:6153export")

    raw = run_backtest(str(tmp_path))
    payload = json.loads(raw)

    assert payload["status"] == "error"
    assert payload["reason"] == "invalid_proxy_env"
    assert "Malformed proxy environment variable HTTPS_PROXY" in payload["error"]


def test_run_backtest_classifies_market_data_network_failures(tmp_path, monkeypatch):
    from src.tools.backtest_tool import run_backtest

    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(key, raising=False)

    (tmp_path / "code").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "source": "auto",
                "codes": ["AAPL.US", "BTC-USDT"],
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "initial_cash": 100000,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (tmp_path / "code" / "signal_engine.py").write_text(
        "class SignalEngine:\n    def generate(self, data_map):\n        return {}\n",
        encoding="utf-8",
    )

    with patch("src.tools.backtest_tool.Runner") as MockRunner:
        runner = MockRunner.return_value
        runner.execute.return_value = MagicMock(
            success=False,
            exit_code=1,
            stdout=(
                "[WARN] yfinance returned no usable data for AAPL\n"
                "[WARN] failed to fetch BTC-USDT: HTTPSConnectionPool(host='www.okx.com', port=443): "
                "Max retries exceeded with url: /api/v5/market/candles\n"
                "{\"error\": \"No data fetched\"}\n"
            ),
            stderr="",
            artifacts={},
        )
        raw = run_backtest(str(tmp_path))

    payload = json.loads(raw)
    assert payload["status"] == "error"
    assert payload["reason"] == "market_data_network_error"
    assert "Outbound market-data requests failed" in payload["diagnosis"]
    assert payload["detail"]["providers"] == ["yfinance", "okx"]
    assert payload["detail"]["proxy_env"] == {
        "HTTP_PROXY": False,
        "HTTPS_PROXY": False,
        "ALL_PROXY": False,
        "NO_PROXY": False,
    }


def test_setup_backtest_run_sanitizes_invalid_signal_engine_annotations(tmp_path):
    from src.vibe_trading_helper import _setup_backtest_run

    raw = _setup_backtest_run(
        {
            "base_dir": str(tmp_path),
            "config_json": json.dumps(
                {
                    "source": "yfinance",
                    "codes": ["AAPL.US"],
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "initial_cash": 100000,
                }
            ),
            "signal_engine_py": (
                "from typing import Dict, Series, DataFrame\n"
                "class SignalEngine:\n"
                "    def generate(self, data_map: Dict[str, DataFrame]) -> Dict[str, Series]:\n"
                "        return {}\n"
            ),
        }
    )

    payload = json.loads(raw)
    assert payload["status"] == "ok"

    signal_source = (
        Path(payload["run_dir"]) / "code" / "signal_engine.py"
    ).read_text(encoding="utf-8")
    assert "from typing import Dict" in signal_source
    assert "Series, DataFrame" not in signal_source
    assert "Dict[str, pd.DataFrame]" in signal_source
    assert "Dict[str, pd.Series]" in signal_source
    assert "import pandas as pd" in signal_source


def test_setup_backtest_run_decodes_escaped_newline_source(tmp_path):
    from src.vibe_trading_helper import _setup_backtest_run

    raw = _setup_backtest_run(
        {
            "base_dir": str(tmp_path),
            "config_json": json.dumps(
                {
                    "source": "yfinance",
                    "codes": ["AAPL.US"],
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "initial_cash": 100000,
                }
            ),
            "signal_engine_py": (
                "import pandas as pd\\n\\n"
                "class SignalEngine:\\n"
                "    def generate(self, data_map):\\n"
                "        return {code: pd.Series(0.0, index=df.index) for code, df in data_map.items()}\\n"
            ),
        }
    )

    payload = json.loads(raw)
    signal_source = (
        Path(payload["run_dir"]) / "code" / "signal_engine.py"
    ).read_text(encoding="utf-8")
    assert "\\n" not in signal_source
    assert "class SignalEngine:" in signal_source


def test_runner_load_module_sanitizes_invalid_signal_engine_annotations(tmp_path):
    pd = pytest.importorskip("pandas")

    from backtest.runner import _load_module_from_file

    signal_path = tmp_path / "signal_engine.py"
    signal_path.write_text(
        "from typing import Dict, Series, DataFrame\n"
        "import pandas as pd\n\n"
        "class SignalEngine:\n"
        "    def generate(self, data_map: Dict[str, DataFrame]) -> Dict[str, Series]:\n"
        "        return {code: pd.Series(0.0, index=df.index) for code, df in data_map.items()}\n",
        encoding="utf-8",
    )

    module = _load_module_from_file(signal_path, "test_signal_engine_module")
    engine = module.SignalEngine()
    frame = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.date_range("2024-01-01", periods=2))
    result = engine.generate({"AAPL.US": frame})

    assert list(result) == ["AAPL.US"]
    assert result["AAPL.US"].index.equals(frame.index)


def test_runner_load_module_decodes_escaped_newline_source(tmp_path):
    pd = pytest.importorskip("pandas")

    from backtest.runner import _load_module_from_file

    signal_path = tmp_path / "signal_engine.py"
    signal_path.write_text(
        "import pandas as pd\\n\\n"
        "class SignalEngine:\\n"
        "    def generate(self, data_map):\\n"
        "        return {code: pd.Series(0.0, index=df.index) for code, df in data_map.items()}\\n",
        encoding="utf-8",
    )

    module = _load_module_from_file(signal_path, "test_signal_engine_escaped_module")
    engine = module.SignalEngine()
    frame = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.date_range("2024-01-01", periods=2))
    result = engine.generate({"AAPL.US": frame})

    assert result["AAPL.US"].index.equals(frame.index)
