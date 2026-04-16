"""Factory for channel-specific visualization adapters."""

from __future__ import annotations

from functools import lru_cache

from .base import BaseVisualizationAdapter
from .feishu_visualization_adapter import FeishuVisualizationAdapter
from .web_visualization_adapter import WebVisualizationAdapter


@lru_cache(maxsize=8)
def _get_visualization_adapter_by_normalized_channel(channel: str) -> BaseVisualizationAdapter:
    if channel == "web":
        return WebVisualizationAdapter()
    if channel == "feishu":
        return FeishuVisualizationAdapter()
    raise ValueError(f"Unsupported visualization adapter channel: {channel}")


def get_visualization_adapter(channel: str) -> BaseVisualizationAdapter:
    normalized = (channel or "web").strip().lower()
    if normalized in {"", "web", "webui"}:
        normalized = "web"
    return _get_visualization_adapter_by_normalized_channel(normalized)


def get_feishu_visualization_adapter() -> FeishuVisualizationAdapter:
    adapter = get_visualization_adapter("feishu")
    assert isinstance(adapter, FeishuVisualizationAdapter)
    return adapter