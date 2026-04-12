"""Tests for XKB adapter — mock-based and optional live X11."""

from __future__ import annotations

import os
import pytest

from lswitch.platform.xkb_adapter import IXKBAdapter, LayoutInfo, X11XKBAdapter

# Re-use the mock from conftest
from tests.conftest import MockXKBAdapter

DISPLAY = os.environ.get("DISPLAY")


# ---------------------------------------------------------------------------
# Mock-based tests (always run)
# ---------------------------------------------------------------------------

class TestMockXKBAdapter:
    """IXKBAdapter interface contract verified via MockXKBAdapter."""

    def test_get_layouts(self, mock_xkb: MockXKBAdapter):
        layouts = mock_xkb.get_layouts()
        assert len(layouts) == 2
        assert layouts[0].name == "en"
        assert layouts[1].name == "ru"

    def test_get_current_layout(self, mock_xkb: MockXKBAdapter):
        cur = mock_xkb.get_current_layout()
        assert isinstance(cur, LayoutInfo)
        assert cur.name == "en"
        assert cur.index == 0

    def test_switch_layout_toggle(self, mock_xkb: MockXKBAdapter):
        """switch_layout() with no target toggles cyclically."""
        first = mock_xkb.switch_layout()
        assert first.name == "ru"
        second = mock_xkb.switch_layout()
        assert second.name == "en"

    def test_switch_layout_target(self, mock_xkb: MockXKBAdapter):
        """switch_layout(target) jumps to exact layout."""
        ru = LayoutInfo(name="ru", index=1, xkb_name="ru")
        result = mock_xkb.switch_layout(target=ru)
        assert result.name == "ru"
        assert mock_xkb.get_current_layout().name == "ru"

    def test_keycode_to_char(self, mock_xkb: MockXKBAdapter):
        """Basic keycode → char mapping (delegated to key_mapper)."""
        en = LayoutInfo(name="en", index=0, xkb_name="us")
        ch = mock_xkb.keycode_to_char(16, en)  # 'q'
        assert ch == "q"

    def test_keycode_to_char_shift(self, mock_xkb: MockXKBAdapter):
        en = LayoutInfo(name="en", index=0, xkb_name="us")
        ch = mock_xkb.keycode_to_char(16, en, shift=True)
        assert ch == "Q"

    def test_implements_interface(self, mock_xkb: MockXKBAdapter):
        assert isinstance(mock_xkb, IXKBAdapter)

    def test_layout_info_fields(self):
        li = LayoutInfo(name="en", index=0, xkb_name="us")
        assert li.name == "en"
        assert li.index == 0
        assert li.xkb_name == "us"

    def test_three_layouts(self):
        adapter = MockXKBAdapter(layouts=["en", "ru", "de"])
        layouts = adapter.get_layouts()
        assert len(layouts) == 3
        # Toggle through all three
        adapter.switch_layout()  # → ru
        adapter.switch_layout()  # → de
        cur = adapter.switch_layout()  # → en (wrap)
        assert cur.name == "en"


# ---------------------------------------------------------------------------
# Live X11 tests (skipped when no DISPLAY — safe for CI)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not DISPLAY, reason="No DISPLAY — X11 tests skipped")
class TestX11XKBAdapterLive:
    """Integration with real X11. Skipped on headless CI."""

    def test_instance_creates(self):
        adapter = X11XKBAdapter()
        assert isinstance(adapter, IXKBAdapter)

    def test_get_layouts_returns_list(self):
        adapter = X11XKBAdapter()
        layouts = adapter.get_layouts()
        assert isinstance(layouts, list)
        assert len(layouts) >= 1
        assert all(isinstance(li, LayoutInfo) for li in layouts)

    def test_get_current_layout_returns_layout_info(self):
        adapter = X11XKBAdapter()
        cur = adapter.get_current_layout()
        assert isinstance(cur, LayoutInfo)
        assert cur.name in [li.name for li in adapter.get_layouts()]

    def test_switch_layout_and_back(self):
        adapter = X11XKBAdapter()
        layouts = adapter.get_layouts()
        if len(layouts) < 2:
            pytest.skip("Only one layout configured")
        original = adapter.get_current_layout()
        switched = adapter.switch_layout()
        assert switched.index != original.index
        # Switch back
        adapter.switch_layout(target=original)
        restored = adapter.get_current_layout()
        assert restored.index == original.index

    def test_keycode_to_char_q(self):
        adapter = X11XKBAdapter()
        layouts = adapter.get_layouts()
        en_layout = None
        for li in layouts:
            if li.name == "en":
                en_layout = li
                break
        if en_layout is None:
            pytest.skip("No 'en' layout configured")
        ch = adapter.keycode_to_char(16, en_layout)  # 'q' on QWERTY
        assert ch == "q"
