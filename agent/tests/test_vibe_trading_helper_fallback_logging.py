from __future__ import annotations

import builtins
import logging
from pathlib import Path

from src import vibe_trading_helper


def _raise_runtime_env_import(name, *args, **kwargs):
    if name == "runtime_env":
        raise ImportError("boom")
    return _ORIGINAL_IMPORT(name, *args, **kwargs)


_ORIGINAL_IMPORT = builtins.__import__


def test_get_fallback_runs_dir_logs_import_failure(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger=vibe_trading_helper.logger.name)
    monkeypatch.setattr(builtins, "__import__", _raise_runtime_env_import)

    result = vibe_trading_helper._get_fallback_runs_dir()

    assert result == Path(vibe_trading_helper._AGENT_ROOT) / "runs"
    assert "Failed to resolve runtime runs dir" in caplog.text
    assert "boom" in caplog.text


def test_get_fallback_swarm_runs_dir_logs_import_failure(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger=vibe_trading_helper.logger.name)
    monkeypatch.setattr(builtins, "__import__", _raise_runtime_env_import)

    result = vibe_trading_helper._get_fallback_swarm_runs_dir()

    assert result == Path(vibe_trading_helper._AGENT_ROOT) / ".swarm" / "runs"
    assert "Failed to resolve runtime swarm runs dir" in caplog.text
    assert "boom" in caplog.text