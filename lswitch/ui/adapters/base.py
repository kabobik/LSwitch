"""BaseUIAdapter — abstract interface for DE-specific UI."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseUIAdapter(ABC):
    @abstractmethod
    def show_menu(self) -> None: ...

    @abstractmethod
    def update_layout_indicator(self, layout_name: str) -> None: ...
