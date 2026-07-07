"""Tests for layout lookup helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.layout_service import LayoutService
from lswitch.platform.xkb_adapter import LayoutInfo


def test_layout_to_lang_defaults_to_en():
    assert LayoutService.layout_to_lang(None) == "en"
    assert LayoutService.layout_to_lang(LayoutInfo("de", 2, "de")) == "en"


def test_layout_to_lang_detects_ru_by_name_or_xkb_name():
    assert LayoutService.layout_to_lang(LayoutInfo("ru", 1, "ru")) == "ru"
    assert LayoutService.layout_to_lang(LayoutInfo("Russian", 1, "us")) == "ru"
    assert LayoutService.layout_to_lang(LayoutInfo("custom", 1, "ru")) == "ru"


def test_find_layout_for_lang_matches_en_ru_and_exact_names():
    en = LayoutInfo("en", 0, "us")
    ru = LayoutInfo("custom-ru", 1, "ru")
    de = LayoutInfo("de", 2, "de")
    layouts = [en, ru, de]

    assert LayoutService.find_layout_for_lang(layouts, "en") is en
    assert LayoutService.find_layout_for_lang(layouts, "ru") is ru
    assert LayoutService.find_layout_for_lang(layouts, "de") is de
    assert LayoutService.find_layout_for_lang(layouts, None) is None
    assert LayoutService.find_layout_for_lang(layouts, "fr") is None


def test_find_available_layout_for_lang_uses_xkb_safely():
    ru = LayoutInfo("ru", 1, "ru")
    xkb = MagicMock()
    xkb.get_layouts.return_value = [LayoutInfo("en", 0, "us"), ru]
    service = LayoutService(xkb)

    assert service.find_available_layout_for_lang("ru") is ru

    xkb.get_layouts.side_effect = RuntimeError("xkb unavailable")
    assert service.find_available_layout_for_lang("ru") is None
