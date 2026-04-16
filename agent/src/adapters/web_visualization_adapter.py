"""Web visualization adapter placeholder for canonical web rendering policy."""

from __future__ import annotations

from .base import BaseVisualizationAdapter


class WebVisualizationAdapter(BaseVisualizationAdapter):
    @property
    def channel(self) -> str:
        return "web"
