"""Shared pytest fixtures for LSwitch 2.0 tests."""

from __future__ import annotations

import pytest

from lswitch.core.event_bus import EventBus
from lswitch.core.state_manager import StateManager
from lswitch.platform.xkb_adapter import IXKBAdapter, LayoutInfo
from lswitch.platform.selection_adapter import ISelectionAdapter, SelectionInfo
from lswitch.platform.system_adapter import CommandResult, ISystemAdapter


# ---------------------------------------------------------------------------
# Mock adapters
# ---------------------------------------------------------------------------

class MockXKBAdapter(IXKBAdapter):
    def __init__(self, layouts: list[str] = None):
        names = layouts or ["en", "ru"]
        self._layouts = [LayoutInfo(n, i, "us" if n == "en" else n) for i, n in enumerate(names)]
        self._current = 0

    def get_layouts(self) -> list[LayoutInfo]:
        return self._layouts

    def get_current_layout(self) -> LayoutInfo:
        return self._layouts[self._current]

    def switch_layout(self, target=None) -> LayoutInfo:
        if target is not None:
            self._current = target.index
        else:
            self._current = (self._current + 1) % len(self._layouts)
        return self._layouts[self._current]

    def keycode_to_char(self, keycode: int, layout: LayoutInfo, shift: bool = False) -> str:
        from lswitch.input.key_mapper import keycode_to_char
        return keycode_to_char(keycode, layout.name, shift)


class MockSelectionAdapter(ISelectionAdapter):
    def __init__(self):
        self._selection = SelectionInfo(text="", owner_id=0, timestamp=0.0)
        self._owner_counter = 0
        self._freshness_threshold = 0.5

    def set_selection(self, text: str) -> None:
        import time
        self._owner_counter += 1
        self._selection = SelectionInfo(text=text, owner_id=self._owner_counter, timestamp=time.time())

    def get_selection(self) -> SelectionInfo:
        return self._selection

    def has_fresh_selection(self, threshold: float = 0.5) -> bool:
        import time
        return bool(self._selection.text) and (time.time() - self._selection.timestamp) < threshold

    def replace_selection(self, new_text: str) -> bool:
        self.set_selection(new_text)
        return True

    def expand_selection_to_word(self) -> SelectionInfo:
        return self._selection


class MockSystemAdapter(ISystemAdapter):
    def run_command(self, args: list[str], timeout: float = 1.0) -> CommandResult:
        return CommandResult(stdout="", stderr="", returncode=0)

    def xdotool_key(self, sequence: str, timeout: float = 0.3) -> None:
        pass

    def get_clipboard(self, selection: str = "primary") -> str:
        return ""

    def set_clipboard(self, text: str, selection: str = "clipboard") -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def state_manager():
    return StateManager(double_click_timeout=0.3, debug=True)


@pytest.fixture
def mock_xkb():
    return MockXKBAdapter()


@pytest.fixture
def mock_selection():
    return MockSelectionAdapter()


@pytest.fixture
def mock_system():
    return MockSystemAdapter()
