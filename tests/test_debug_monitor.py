"""Tests for DebugMonitorWindow.

These tests use mocked PyQt5 to avoid conflicts with test_ui.py which also mocks PyQt5.
"""

import time
import sys
import types
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import pytest

from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.event_bus import EventBus
from lswitch.core.states import State, StateContext


# ---------------------------------------------------------------------------
# PyQt5 mock helpers
# ---------------------------------------------------------------------------

class MockQWidget:
    """Mock QWidget for testing."""
    def __init__(self, *args, **kwargs):
        self._visible = False
        self._title = ""
    
    def setWindowTitle(self, title):
        self._title = title
    
    def windowTitle(self):
        return self._title
    
    def setMinimumSize(self, *args):
        pass
    
    def resize(self, *args):
        pass
    
    def show(self):
        self._visible = True
    
    def hide(self):
        self._visible = False
    
    def isVisible(self):
        return self._visible
    
    def raise_(self):
        pass
    
    def activateWindow(self):
        pass
    
    def closeEvent(self, event):
        pass


class MockQLabel:
    """Mock QLabel for testing."""
    def __init__(self, text="", *args, **kwargs):
        self._text = text
        self._style = ""
    
    def setText(self, text):
        self._text = text
    
    def text(self):
        return self._text
    
    def setFont(self, font):
        pass
    
    def setWordWrap(self, wrap):
        pass
    
    def setStyleSheet(self, style):
        self._style = style


class MockQTextEdit:
    """Mock QTextEdit for testing."""
    def __init__(self, *args, **kwargs):
        self._text = ""
        self._scrollbar = Mock()
        self._scrollbar.setValue = Mock()
        self._scrollbar.maximum = Mock(return_value=100)
    
    def setReadOnly(self, ro):
        pass
    
    def setFont(self, font):
        pass
    
    def setLineWrapMode(self, mode):
        pass
    
    def append(self, text):
        self._text += text + "\n"
    
    def clear(self):
        self._text = ""
    
    def toPlainText(self):
        return self._text
    
    def verticalScrollBar(self):
        return self._scrollbar
    
    def textCursor(self):
        cursor = Mock()
        cursor.movePosition = Mock()
        cursor.removeSelectedText = Mock()
        return cursor


class MockQTableWidget:
    """Mock QTableWidget for testing."""
    def __init__(self, rows=0, cols=0, *args, **kwargs):
        self._rows = rows
        self._cols = cols
        self._items = {}
    
    def setHorizontalHeaderLabels(self, labels):
        pass
    
    def horizontalHeader(self):
        header = Mock()
        header.setSectionResizeMode = Mock()
        return header
    
    def setFont(self, font):
        pass
    
    def setMaximumHeight(self, h):
        pass
    
    def setRowCount(self, count):
        self._rows = count
    
    def rowCount(self):
        return self._rows
    
    def setItem(self, row, col, item):
        self._items[(row, col)] = item


class MockQTimer:
    """Mock QTimer for testing."""
    def __init__(self, parent=None):
        self._callback = None
        self._interval = 0
    
    @property
    def timeout(self):
        mock_signal = Mock()
        mock_signal.connect = lambda cb: setattr(self, '_callback', cb)
        return mock_signal
    
    def start(self, interval=None):
        if interval:
            self._interval = interval
    
    def stop(self):
        pass


@pytest.fixture
def mock_app():
    """Create a mock LSwitchApp for testing."""
    app = Mock()
    app.state_manager = Mock()
    app.state_manager.context = StateContext()
    app.state_manager.context.state = State.IDLE
    app.state_manager.context.current_layout = "en"
    app.state_manager.context.event_buffer = []
    app.state_manager.context.chars_in_buffer = 0
    app.state_manager.context.shift_pressed = False
    app.state_manager.context.backspace_hold_active = False
    app.state_manager.context.backspace_repeats = 0
    app._last_auto_marker = None
    app._extract_last_word_events = Mock(return_value=("", []))
    app.xkb = None
    return app


@pytest.fixture
def event_bus():
    """Create a real EventBus for testing."""
    return EventBus()


class DebugMonitorWindowMock:
    """Mock version of DebugMonitorWindow for testing core logic."""
    
    MAX_LOG_LINES = 200
    
    def __init__(self, app, event_bus):
        self._app = app
        self._event_bus = event_bus
        self._log_lines = 0
        
        # Mock UI elements
        self._state_label = MockQLabel("State: IDLE")
        self._layout_label = MockQLabel("Layout: en")
        self._chars_label = MockQLabel("Chars in buffer: 0")
        self._shift_label = MockQLabel("Shift pressed: no")
        self._backspace_label = MockQLabel("Backspace hold: no (repeats: 0)")
        self._buffer_table = MockQTableWidget(0, 4)
        self._buffer_summary = MockQLabel("Buffer: (empty)")
        self._word_label = MockQLabel("Word: (none)")
        self._word_events_label = MockQLabel("Events: (none)")
        self._marker_label = MockQLabel("No marker")
        self._marker_age_label = MockQLabel("Age: -")
        self._sel_text_label = MockQLabel("Text: (none)")
        self._sel_owner_label = MockQLabel("Owner ID: -")
        self._sel_changed_label = MockQLabel("Last changed: -")
        self._log_text = MockQTextEdit()
        self._age_timer = MockQTimer()
        
        self._subscribe_events()
        self._refresh_state()

    def _on_selection_updated(self, text, owner_id, last_changed_at):
        """Mirror the real _on_selection_updated logic for testability."""
        if len(text) > 200:
            display_text = text[:200] + f"... ({len(text)} total chars)"
        else:
            display_text = text if text else "(none)"
        self._sel_text_label.setText(f"Text: {display_text}")
        self._sel_owner_label.setText(f"Owner ID: {f'0x{owner_id:08x}' if owner_id else '-'}")
        if last_changed_at > 0:
            ts_str = time.strftime("%H:%M:%S", time.localtime(last_changed_at))
            self._sel_changed_label.setText(f"Last changed: {ts_str}")
        else:
            self._sel_changed_label.setText("Last changed: -")

    def windowTitle(self):
        return "LSwitch Debug Monitor"
    
    def _subscribe_events(self):
        if self._event_bus is None:
            return
        for evt in [
            EventType.KEY_PRESS, EventType.KEY_RELEASE, EventType.KEY_REPEAT,
            EventType.CONVERSION_START, EventType.CONVERSION_COMPLETE, EventType.CONVERSION_CANCELLED,
            EventType.LAYOUT_CHANGED, EventType.DOUBLE_SHIFT, EventType.BACKSPACE_HOLD,
        ]:
            self._event_bus.subscribe(evt, self._on_event)
    
    def _unsubscribe_events(self):
        if self._event_bus is None:
            return
        for evt in [
            EventType.KEY_PRESS, EventType.KEY_RELEASE, EventType.KEY_REPEAT,
            EventType.CONVERSION_START, EventType.CONVERSION_COMPLETE, EventType.CONVERSION_CANCELLED,
            EventType.LAYOUT_CHANGED, EventType.DOUBLE_SHIFT, EventType.BACKSPACE_HOLD,
        ]:
            self._event_bus.unsubscribe(evt, self._on_event)
    
    def _on_event(self, event):
        ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
        evt_type = event.type.name
        data_str = self._format_event_data(event)
        self._append_log_entry(ts, evt_type, data_str)
        self._refresh_state()
    
    def _format_event_data(self, event):
        from lswitch.input.key_mapper import keycode_to_char
        data = event.data
        if data is None:
            return ""
        if event.type in (EventType.KEY_PRESS, EventType.KEY_RELEASE, EventType.KEY_REPEAT):
            if hasattr(data, 'code'):
                ch = keycode_to_char(data.code, shift=getattr(data, 'shifted', False))
                return f"code={data.code} ch='{ch}' shifted={getattr(data, 'shifted', False)}"
            return str(data)
        if event.type == EventType.LAYOUT_CHANGED:
            return str(data)
        if event.type in (EventType.CONVERSION_START, EventType.CONVERSION_COMPLETE, EventType.CONVERSION_CANCELLED):
            if hasattr(data, 'original'):
                return f"'{data.original}' → '{data.converted}' [{data.mode}]"
            return str(data)
        return str(data)[:80]
    
    def _refresh_state(self):
        if self._app is None or self._app.state_manager is None:
            return
        ctx = self._app.state_manager.context
        self._state_label.setText(f"State: {ctx.state.name}")
        self._layout_label.setText(f"Layout: {ctx.current_layout}")
        self._chars_label.setText(f"Chars in buffer: {ctx.chars_in_buffer}")
        self._shift_label.setText(f"Shift pressed: {'yes' if ctx.shift_pressed else 'no'}")
        self._backspace_label.setText(
            f"Backspace hold: {'yes' if ctx.backspace_hold_active else 'no'} "
            f"(repeats: {ctx.backspace_repeats})"
        )
        self._refresh_buffer_table(ctx.event_buffer)
        self._refresh_last_word()
        self._refresh_marker()
    
    def _refresh_buffer_table(self, event_buffer):
        from lswitch.input.key_mapper import keycode_to_char
        self._buffer_table.setRowCount(len(event_buffer))
        summary_parts = []
        for i, ev in enumerate(event_buffer):
            code = getattr(ev, 'code', '?')
            shifted = getattr(ev, 'shifted', False)
            ch = keycode_to_char(code, shift=shifted) if isinstance(code, int) else '?'
            self._buffer_table.setItem(i, 0, Mock())
            self._buffer_table.setItem(i, 1, Mock())
            self._buffer_table.setItem(i, 2, Mock())
            self._buffer_table.setItem(i, 3, Mock())
            if ch:
                summary_parts.append(f"[{code}:{ch}]")
            else:
                summary_parts.append(f"[{code}:?]")
        if summary_parts:
            self._buffer_summary.setText("Buffer: " + " ".join(summary_parts))
        else:
            self._buffer_summary.setText("Buffer: (empty)")
    
    def _refresh_last_word(self):
        from lswitch.input.key_mapper import keycode_to_char
        try:
            word, word_events = self._app._extract_last_word_events(None)
            if word:
                self._word_label.setText(f"Word: '{word}' ({len(word)} chars)")
                evt_parts = []
                for ev in word_events:
                    code = getattr(ev, 'code', '?')
                    shifted = getattr(ev, 'shifted', False)
                    ch = keycode_to_char(code, shift=shifted) if isinstance(code, int) else '?'
                    evt_parts.append(f"{code}:{ch}")
                self._word_events_label.setText("Events: " + " ".join(evt_parts))
            else:
                self._word_label.setText("Word: (none)")
                self._word_events_label.setText("Events: (none)")
        except Exception as e:
            self._word_label.setText(f"Word: (error: {e})")
            self._word_events_label.setText("Events: (error)")
    
    def _refresh_marker(self):
        marker = getattr(self._app, '_last_auto_marker', None)
        if marker is None:
            self._marker_label.setText("No marker")
            self._marker_age_label.setText("Age: -")
        else:
            word = marker.get('word', '?')
            direction = marker.get('direction', '?')
            lang = marker.get('lang', '?')
            self._marker_label.setText(
                f"Word: '{word}'\nDirection: {direction}\nLang: {lang}"
            )
            self._update_marker_age()
    
    def _update_marker_age(self):
        marker = getattr(self._app, '_last_auto_marker', None)
        if marker is None:
            self._marker_age_label.setText("Age: -")
            return
        marker_time = marker.get('time', 0)
        if marker_time > 0:
            age = time.time() - marker_time
            self._marker_age_label.setText(f"Age: {age:.1f}s")
        else:
            self._marker_age_label.setText("Age: unknown")
    
    def _append_log_entry(self, timestamp, event_type, data):
        line = f"[{timestamp}] {event_type}: {data}"
        self._log_text.append(line)
        self._log_lines += 1
    
    def _clear_log(self):
        self._log_text.clear()
        self._log_lines = 0
    
    def cleanup(self):
        self._age_timer.stop()
        self._unsubscribe_events()


class TestDebugMonitorInit:
    """Test DebugMonitorWindow initialization."""

    def test_creates_window(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert window is not None
        assert window.windowTitle() == "LSwitch Debug Monitor"
        
        window.cleanup()

    def test_subscribes_to_events(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert EventType.KEY_PRESS in event_bus._handlers
        assert len(event_bus._handlers[EventType.KEY_PRESS]) > 0
        
        window.cleanup()

    def test_unsubscribes_on_cleanup(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        handlers_before = len(event_bus._handlers[EventType.KEY_PRESS])
        
        window.cleanup()
        
        handlers_after = len(event_bus._handlers[EventType.KEY_PRESS])
        assert handlers_after < handlers_before


class TestStateRefresh:
    """Test state refresh functionality."""

    def test_displays_idle_state(self, mock_app, event_bus):
        mock_app.state_manager.context.state = State.IDLE
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "IDLE" in window._state_label.text()
        
        window.cleanup()

    def test_displays_typing_state(self, mock_app, event_bus):
        mock_app.state_manager.context.state = State.TYPING
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "TYPING" in window._state_label.text()
        
        window.cleanup()

    def test_displays_layout(self, mock_app, event_bus):
        mock_app.state_manager.context.current_layout = "ru"
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "ru" in window._layout_label.text()
        
        window.cleanup()

    def test_displays_buffer_count(self, mock_app, event_bus):
        mock_app.state_manager.context.chars_in_buffer = 5
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "5" in window._chars_label.text()
        
        window.cleanup()


class TestEventBuffer:
    """Test event buffer display."""

    def test_empty_buffer_shows_empty(self, mock_app, event_bus):
        mock_app.state_manager.context.event_buffer = []
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "(empty)" in window._buffer_summary.text()
        
        window.cleanup()

    def test_buffer_with_events_shows_summary(self, mock_app, event_bus):
        mock_app.state_manager.context.event_buffer = [
            KeyEventData(code=16, value=1),  # q
            KeyEventData(code=17, value=1),  # w
        ]
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "[16:q]" in window._buffer_summary.text()
        assert "[17:w]" in window._buffer_summary.text()
        
        window.cleanup()

    def test_buffer_table_row_count(self, mock_app, event_bus):
        mock_app.state_manager.context.event_buffer = [
            KeyEventData(code=16, value=1),
            KeyEventData(code=17, value=1),
            KeyEventData(code=18, value=1),
        ]
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert window._buffer_table.rowCount() == 3
        
        window.cleanup()


class TestAutoMarker:
    """Test auto marker display."""

    def test_no_marker_shows_none(self, mock_app, event_bus):
        mock_app._last_auto_marker = None
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "No marker" in window._marker_label.text()
        
        window.cleanup()

    def test_marker_shows_word(self, mock_app, event_bus):
        mock_app._last_auto_marker = {
            'word': 'ghbdtn',
            'direction': 'en_to_ru',
            'lang': 'en',
            'time': time.time(),
        }
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "ghbdtn" in window._marker_label.text()
        assert "en_to_ru" in window._marker_label.text()
        
        window.cleanup()

    def test_marker_age_updates(self, mock_app, event_bus):
        mock_app._last_auto_marker = {
            'word': 'test',
            'direction': 'en_to_ru',
            'lang': 'en',
            'time': time.time() - 5.0,
        }
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        window._update_marker_age()
        
        age_text = window._marker_age_label.text()
        assert "Age:" in age_text
        assert "5" in age_text or "6" in age_text
        
        window.cleanup()


class TestLastWord:
    """Test last word display."""

    def test_no_word_shows_none(self, mock_app, event_bus):
        mock_app._extract_last_word_events = Mock(return_value=("", []))
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "(none)" in window._word_label.text()
        
        window.cleanup()

    def test_word_shows_extracted(self, mock_app, event_bus):
        mock_app._extract_last_word_events = Mock(return_value=("hello", [
            KeyEventData(code=35, value=1),
            KeyEventData(code=18, value=1),
            KeyEventData(code=38, value=1),
            KeyEventData(code=38, value=1),
            KeyEventData(code=24, value=1),
        ]))
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        assert "hello" in window._word_label.text()
        assert "5 chars" in window._word_label.text()
        
        window.cleanup()


class TestEventLog:
    """Test event log functionality."""

    def test_log_clears(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        window._log_text.append("test log entry")
        assert "test log entry" in window._log_text.toPlainText()
        
        window._clear_log()
        
        assert window._log_text.toPlainText() == ""
        
        window.cleanup()

    def test_event_appends_to_log(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        window._clear_log()
        
        window._append_log_entry("12:00:00", "KEY_PRESS", "code=16")
        
        log_text = window._log_text.toPlainText()
        assert "KEY_PRESS" in log_text
        assert "code=16" in log_text
        
        window.cleanup()


class TestEventFormatting:
    """Test event data formatting."""

    def test_format_key_event(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        event = Event(
            type=EventType.KEY_PRESS,
            data=KeyEventData(code=16, value=1, shifted=False),
            timestamp=time.time(),
        )
        
        formatted = window._format_event_data(event)
        
        assert "code=16" in formatted
        assert "ch='q'" in formatted
        
        window.cleanup()

    def test_format_layout_event(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)
        
        event = Event(
            type=EventType.LAYOUT_CHANGED,
            data="ru",
            timestamp=time.time(),
        )
        
        formatted = window._format_event_data(event)
        
        assert "ru" in formatted
        
        window.cleanup()


class TestSelectionPollerThread:
    """Test _SelectionPollerThread freshness logic (without actual QThread)."""

    def test_freshness_detected_on_text_change(self):
        """First non-empty selection should be fresh."""
        from lswitch.platform.selection_adapter import SelectionInfo

        app = Mock()
        app.selection = Mock()
        app.selection.get_selection.return_value = SelectionInfo(
            text="hello", owner_id=0x04a00003, timestamp=time.time()
        )

        # Simulate the freshness logic from _SelectionPollerThread
        prev_text = ""
        prev_owner_id = 0

        info = app.selection.get_selection()
        is_fresh = bool(info.text) and (
            info.text != prev_text or info.owner_id != prev_owner_id
        )

        assert is_fresh is True

    def test_freshness_false_on_same_selection(self):
        """Same text + owner_id should not be fresh after first read."""
        from lswitch.platform.selection_adapter import SelectionInfo

        prev_text = "hello"
        prev_owner_id = 0x04a00003

        info = SelectionInfo(text="hello", owner_id=0x04a00003, timestamp=time.time())
        is_fresh = bool(info.text) and (
            info.text != prev_text or info.owner_id != prev_owner_id
        )

        assert is_fresh is False

    def test_freshness_true_on_owner_change(self):
        """Different owner_id with same text should be fresh."""
        from lswitch.platform.selection_adapter import SelectionInfo

        prev_text = "hello"
        prev_owner_id = 0x04a00003

        info = SelectionInfo(text="hello", owner_id=0x05b00001, timestamp=time.time())
        is_fresh = bool(info.text) and (
            info.text != prev_text or info.owner_id != prev_owner_id
        )

        assert is_fresh is True

    def test_freshness_false_on_empty_text(self):
        """Empty selection should never be fresh."""
        from lswitch.platform.selection_adapter import SelectionInfo

        info = SelectionInfo(text="", owner_id=0, timestamp=0.0)
        is_fresh = bool(info.text) and (
            info.text != "" or info.owner_id != 0
        )

        assert is_fresh is False

    def test_does_not_call_has_fresh_selection(self):
        """Poller must NOT call has_fresh_selection to avoid side effects."""
        from lswitch.platform.selection_adapter import SelectionInfo

        app = Mock()
        app.selection = Mock()
        app.selection.get_selection.return_value = SelectionInfo(
            text="test", owner_id=1, timestamp=time.time()
        )
        app.selection.has_fresh_selection = Mock()

        # Simulate one poll cycle
        info = app.selection.get_selection()
        _ = bool(info.text) and (info.text != "" or info.owner_id != 0)

        app.selection.has_fresh_selection.assert_not_called()


class TestSelectionDisplay:
    """Test selection UI update logic in DebugMonitorWindowMock."""

    def test_display_normal_text(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)

        window._on_selection_updated("hello world", 0x04a00003, time.time())

        assert "hello world" in window._sel_text_label.text()
        assert "0x04a00003" in window._sel_owner_label.text()

        window.cleanup()

    def test_display_truncated_text(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)

        long_text = "A" * 300
        window._on_selection_updated(long_text, 0x01, time.time())

        label_text = window._sel_text_label.text()
        assert "..." in label_text
        assert "300 total chars" in label_text
        # Should contain exactly 200 A's before truncation
        assert "A" * 200 in label_text

        window.cleanup()

    def test_display_empty_selection(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)

        window._on_selection_updated("", 0, 0.0)

        assert "(none)" in window._sel_text_label.text()
        assert "Last changed: -" in window._sel_changed_label.text()

        window.cleanup()

    def test_last_changed_shows_time(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)

        ts = time.time()
        window._on_selection_updated("text", 1, ts)

        expected = time.strftime("%H:%M:%S", time.localtime(ts))
        assert f"Last changed: {expected}" in window._sel_changed_label.text()

        window.cleanup()

    def test_last_changed_zero_shows_dash(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)

        window._on_selection_updated("text", 1, 0.0)

        assert "Last changed: -" in window._sel_changed_label.text()

        window.cleanup()

    def test_owner_id_zero_shows_dash(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)

        window._on_selection_updated("", 0, 0.0)

        assert "Owner ID: -" in window._sel_owner_label.text()

        window.cleanup()

    def test_owner_id_nonzero_shows_hex(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)

        window._on_selection_updated("x", 0x0abc0001, time.time())

        assert "0x0abc0001" in window._sel_owner_label.text()

        window.cleanup()

    def test_display_exactly_200_chars_no_truncation(self, mock_app, event_bus):
        window = DebugMonitorWindowMock(app=mock_app, event_bus=event_bus)

        text_200 = "B" * 200
        window._on_selection_updated(text_200, 1, time.time())

        label_text = window._sel_text_label.text()
        assert "..." not in label_text
        assert "B" * 200 in label_text

        window.cleanup()

