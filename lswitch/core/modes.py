"""Conversion mode strategy classes."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseMode(ABC):
    @abstractmethod
    def execute(self) -> bool:
        """Execute the conversion. Returns True on success."""


class RetypeMode(BaseMode):
    """Delete typed chars, switch layout, replay events."""

    def execute(self) -> bool:
        raise NotImplementedError


class SelectionMode(BaseMode):
    """Read PRIMARY selection, convert text, paste back."""

    def execute(self) -> bool:
        raise NotImplementedError
