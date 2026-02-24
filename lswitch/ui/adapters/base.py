"""BaseUIAdapter — abstract interface for DE-specific UI."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseUIAdapter(ABC):
    """Base class for desktop-environment-specific UI adapters."""

    def __init__(self):
        self.theme_colors: dict | None = None

    @abstractmethod
    def show_menu(self) -> None: ...

    @abstractmethod
    def update_layout_indicator(self, layout_name: str) -> None: ...

    @abstractmethod
    def create_menu(self, parent=None):
        """Create a menu for the system tray.

        Returns QMenu (native) or QMenuWrapper (custom) depending on DE.
        """
        ...

    def supports_native_menu(self) -> bool:
        """Return True if the DE supports native QMenu with correct theming."""
        return False

    def get_theme_colors(self) -> dict:
        """Return DE theme colors: bg_color, fg_color, base_color (tuples)."""
        return {
            "bg_color": (46, 46, 51),
            "fg_color": (255, 255, 255),
            "base_color": (35, 38, 41),
        }
