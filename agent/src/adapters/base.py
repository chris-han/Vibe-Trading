"""Base classes for deterministic application adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseVisualizationAdapter(ABC):
    """Base type for channel-specific visualization adapters."""

    @property
    @abstractmethod
    def channel(self) -> str:
        """Return the channel identifier handled by this adapter."""
