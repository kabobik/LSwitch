"""Layout lookup helpers used by conversion flows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lswitch.platform.xkb_adapter import IXKBAdapter


class LayoutService:
    """Small EN/RU layout helper before full layout profiles exist."""

    def __init__(self, xkb: "IXKBAdapter | None" = None):
        self.xkb = xkb

    def current_lang(self) -> str:
        if self.xkb is None:
            return "en"
        return self.layout_to_lang(self.xkb.get_current_layout())

    def find_available_layout_for_lang(self, lang: str | None):
        if self.xkb is None:
            return None
        try:
            return self.find_layout_for_lang(self.xkb.get_layouts(), lang)
        except Exception:
            return None

    @staticmethod
    def layout_to_lang(layout_info) -> str:
        if layout_info is None:
            return "en"
        name = getattr(layout_info, "name", "").lower()
        xkb_name = getattr(layout_info, "xkb_name", "").lower()
        if name.startswith("ru") or name in {"russian", "россия"}:
            return "ru"
        if xkb_name.startswith("ru"):
            return "ru"
        return "en"

    @staticmethod
    def find_layout_for_lang(layouts, lang: str | None):
        if not lang:
            return None

        wanted = lang.lower()
        for layout in layouts or []:
            name = getattr(layout, "name", "").lower()
            xkb_name = getattr(layout, "xkb_name", "").lower()
            if wanted == "en" and (name in {"en", "us"} or xkb_name == "us"):
                return layout
            if wanted == "ru" and (name == "ru" or xkb_name.startswith("ru")):
                return layout
            if name == wanted or xkb_name == wanted:
                return layout
        return None
