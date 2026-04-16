from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.factory import get_feishu_visualization_adapter, get_visualization_adapter
from src.adapters.feishu_visualization_adapter import FeishuVisualizationAdapter
from src.adapters.web_visualization_adapter import WebVisualizationAdapter


AGENT_ROOT = Path(__file__).resolve().parents[2]
API_SERVER_PATH = AGENT_ROOT / "api_server.py"


def test_factory_returns_expected_adapter_types():
    assert isinstance(get_visualization_adapter("feishu"), FeishuVisualizationAdapter)
    assert isinstance(get_visualization_adapter("web"), WebVisualizationAdapter)
    assert isinstance(get_visualization_adapter("webui"), WebVisualizationAdapter)
    assert get_visualization_adapter("") is get_visualization_adapter("web")


def test_feishu_factory_helper_returns_cached_feishu_adapter():
    adapter = get_feishu_visualization_adapter()

    assert isinstance(adapter, FeishuVisualizationAdapter)
    assert adapter is get_visualization_adapter("feishu")


def test_factory_rejects_unknown_channel():
    with pytest.raises(ValueError, match="Unsupported visualization adapter channel"):
        get_visualization_adapter("slack")


def test_api_server_uses_adapter_factory_for_feishu_visualization():
    source = API_SERVER_PATH.read_text(encoding="utf-8")

    assert "from src.adapters.factory import get_feishu_visualization_adapter" in source
    assert "_FEISHU_VISUALIZATION_ADAPTER = get_feishu_visualization_adapter()" in source


def test_api_server_does_not_redeclare_legacy_feishu_visualization_helpers():
    source = API_SERVER_PATH.read_text(encoding="utf-8")

    forbidden_symbols = [
        "def _sanitize_vchart_spec(",
        "def _feishu_split_card_elements(",
        "def _feishu_build_card_v2(",
        "def _feishu_build_streaming_card_v2(",
        "def _feishu_render_stream_body(",
        "_VCHART_FENCE_RE =",
    ]

    for symbol in forbidden_symbols:
        assert symbol not in source, f"legacy Feishu visualization helper leaked back into api_server.py: {symbol}"