"""KDEAdapter — KDE Plasma-specific tray/menu."""

from __future__ import annotations

from PyQt5.QtWidgets import QMenu
from PyQt5.QtGui import QPalette, QColor

from lswitch.ui.adapters.base import BaseUIAdapter


class KDEAdapter(BaseUIAdapter):
    """UI adapter for KDE Plasma — uses native QMenu with theme colors."""

    def __init__(self):
        super().__init__()
        self.theme_colors = self.get_theme_colors()

    def show_menu(self) -> None:
        pass  # Menu is shown natively via QSystemTrayIcon.setContextMenu

    def update_layout_indicator(self, layout_name: str) -> None:
        pass  # Handled by TrayIcon.set_layout

    def create_menu(self, parent=None) -> QMenu:
        """Create a native QMenu styled for KDE Plasma."""
        menu = QMenu(None)

        bg = self.theme_colors.get("bg_color", (49, 54, 59))
        fg = self.theme_colors.get("fg_color", (239, 240, 241))
        hover = tuple(min(255, c + 20) for c in bg)

        palette = menu.palette()
        palette.setColor(QPalette.Window, QColor(*bg))
        palette.setColor(QPalette.WindowText, QColor(*fg))
        palette.setColor(QPalette.Base, QColor(*self.theme_colors.get("base_color", bg)))
        palette.setColor(QPalette.Text, QColor(*fg))
        palette.setColor(QPalette.Highlight, QColor(*hover))
        palette.setColor(QPalette.HighlightedText, QColor(*fg))
        menu.setPalette(palette)

        menu.setStyleSheet(
            f"QMenu {{ background-color: rgb({bg[0]},{bg[1]},{bg[2]}); "
            f"color: rgb({fg[0]},{fg[1]},{fg[2]}); padding: 6px; font-size: 11pt; }}"
            f"QMenu::item {{ padding: 8px 20px; min-height: 32px; }}"
            f"QMenu::item:selected {{ background-color: rgb({hover[0]},{hover[1]},{hover[2]}); }}"
            f"QMenu::item:disabled {{ color: rgb(100,100,105); }}"
        )
        return menu

    def supports_native_menu(self) -> bool:
        return True

    def get_theme_colors(self) -> dict:
        # Breeze Dark defaults
        return {
            "bg_color": (49, 54, 59),
            "fg_color": (239, 240, 241),
            "base_color": (35, 38, 41),
        }
