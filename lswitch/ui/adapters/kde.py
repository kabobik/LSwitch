"""KDEAdapter — KDE Plasma-specific tray/menu."""

from __future__ import annotations

from lswitch.ui.adapters.base import BaseUIAdapter


class KDEAdapter(BaseUIAdapter):
    def show_menu(self) -> None:
        raise NotImplementedError

    def update_layout_indicator(self, layout_name: str) -> None:
        raise NotImplementedError
