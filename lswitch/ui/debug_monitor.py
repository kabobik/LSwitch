"""DebugMonitorWindow — real-time buffer and state visualization for LSwitch debugging."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QPushButton,
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont, QColor

from lswitch.core.events import Event, EventType
from lswitch.input.key_mapper import keycode_to_char

if TYPE_CHECKING:
    from lswitch.app import LSwitchApp
    from lswitch.core.event_bus import EventBus


class _SelectionPollerThread(QThread):
    """Background thread polling X11 PRIMARY selection every 500ms."""

    selection_updated = pyqtSignal(str, int, float)  # text, owner_id, last_changed_at

    def __init__(self, app: "LSwitchApp"):
        super().__init__()
        self._app = app
        self._running = True
        self._prev_text: str = ""
        self._prev_owner_id: int = 0
        self._selection_captured_at: float = 0.0  # time when selection last changed

    def run(self):
        while self._running:
            try:
                info = self._app.selection.get_selection()
                changed = (
                    bool(info.text)
                    and (info.text != self._prev_text or info.owner_id != self._prev_owner_id)
                )
                if changed:
                    self._prev_text = info.text
                    self._prev_owner_id = info.owner_id
                    self._selection_captured_at = time.time()
                self.selection_updated.emit(info.text, info.owner_id, self._selection_captured_at)
            except Exception:
                self.selection_updated.emit("(error)", 0, 0.0)
            self.msleep(500)

    def stop(self):
        self._running = False
        self.wait(1000)


class DebugMonitorWindow(QWidget):
    """Non-modal debug window showing buffers and state in real-time.

    Thread-safe: updates from non-GUI threads arrive via Qt signals.
    """

    # Qt signals for thread-safe updates from EventBus handlers
    _update_signal = pyqtSignal()
    _log_event_signal = pyqtSignal(str, str, str)  # timestamp, event_type, data

    MAX_LOG_LINES = 200

    def __init__(self, app: "LSwitchApp", event_bus: "EventBus"):
        super().__init__()
        self._app = app
        self._event_bus = event_bus
        self._log_lines = 0

        self._selection_poller: _SelectionPollerThread | None = None

        self._init_ui()
        self._connect_signals()
        self._subscribe_events()
        self._start_timers()

        # Initial refresh
        self._refresh_state()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _init_ui(self):
        """Build the window layout."""
        self.setWindowTitle("LSwitch Debug Monitor")
        self.setMinimumSize(600, 700)
        self.resize(700, 800)

        # Monospace font for technical data
        mono_font = QFont("Monospace", 9)
        mono_font.setStyleHint(QFont.Monospace)

        main_layout = QVBoxLayout(self)

        # Use splitter for resizable sections
        splitter = QSplitter(Qt.Vertical)

        # -- Section 1: Current State --
        state_group = QGroupBox("Current State")
        state_layout = QVBoxLayout(state_group)

        self._state_label = QLabel("State: IDLE")
        self._state_label.setFont(mono_font)
        state_layout.addWidget(self._state_label)

        self._layout_label = QLabel("Layout: en")
        self._layout_label.setFont(mono_font)
        state_layout.addWidget(self._layout_label)

        self._chars_label = QLabel("Chars in buffer: 0")
        self._chars_label.setFont(mono_font)
        state_layout.addWidget(self._chars_label)

        self._shift_label = QLabel("Shift pressed: no")
        self._shift_label.setFont(mono_font)
        state_layout.addWidget(self._shift_label)

        self._backspace_label = QLabel("Backspace hold: no (repeats: 0)")
        self._backspace_label.setFont(mono_font)
        state_layout.addWidget(self._backspace_label)

        self._sel_valid_label = QLabel("Selection valid: no")
        self._sel_valid_label.setFont(mono_font)
        state_layout.addWidget(self._sel_valid_label)

        splitter.addWidget(state_group)

        # -- Section 2: Event Buffer --
        buffer_group = QGroupBox("Event Buffer (keystroke events)")
        buffer_layout = QVBoxLayout(buffer_group)

        self._buffer_table = QTableWidget(0, 4)
        self._buffer_table.setHorizontalHeaderLabels(["#", "Keycode", "Char", "Shifted"])
        self._buffer_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._buffer_table.setFont(mono_font)
        self._buffer_table.setMaximumHeight(150)
        buffer_layout.addWidget(self._buffer_table)

        self._buffer_summary = QLabel("Buffer: (empty)")
        self._buffer_summary.setFont(mono_font)
        self._buffer_summary.setWordWrap(True)
        buffer_layout.addWidget(self._buffer_summary)

        splitter.addWidget(buffer_group)

        # -- Section 3: Last Word --
        word_group = QGroupBox("Last Word (extracted by _extract_last_word_events)")
        word_layout = QVBoxLayout(word_group)

        self._word_label = QLabel("Word: (none)")
        self._word_label.setFont(QFont("Monospace", 12, QFont.Bold))
        word_layout.addWidget(self._word_label)

        self._word_events_label = QLabel("Events: (none)")
        self._word_events_label.setFont(mono_font)
        self._word_events_label.setWordWrap(True)
        word_layout.addWidget(self._word_events_label)

        splitter.addWidget(word_group)

        # -- Section 4: Auto Marker --
        marker_group = QGroupBox("Auto Marker (_last_auto_marker)")
        marker_layout = QVBoxLayout(marker_group)

        self._marker_label = QLabel("No marker")
        self._marker_label.setFont(mono_font)
        self._marker_label.setWordWrap(True)
        marker_layout.addWidget(self._marker_label)

        self._marker_age_label = QLabel("Age: -")
        self._marker_age_label.setFont(mono_font)
        marker_layout.addWidget(self._marker_age_label)

        splitter.addWidget(marker_group)

        # -- Section 5: X11 PRIMARY Selection --
        selection_group = QGroupBox("X11 PRIMARY Selection")
        selection_layout = QVBoxLayout(selection_group)

        self._sel_text_label = QLabel("Text: (none)")
        self._sel_text_label.setFont(mono_font)
        self._sel_text_label.setWordWrap(True)
        selection_layout.addWidget(self._sel_text_label)

        self._sel_owner_label = QLabel("Owner ID: -")
        self._sel_owner_label.setFont(mono_font)
        selection_layout.addWidget(self._sel_owner_label)

        self._sel_changed_label = QLabel("Last changed: -")
        self._sel_changed_label.setFont(mono_font)
        selection_layout.addWidget(self._sel_changed_label)

        self._prev_sel_text_label = QLabel("Prev text: (none)")
        self._prev_sel_text_label.setFont(mono_font)
        self._prev_sel_text_label.setWordWrap(True)
        selection_layout.addWidget(self._prev_sel_text_label)

        self._prev_sel_owner_label = QLabel("Prev owner: -")
        self._prev_sel_owner_label.setFont(mono_font)
        selection_layout.addWidget(self._prev_sel_owner_label)

        splitter.addWidget(selection_group)

        # -- Section 6: Event Log --
        log_group = QGroupBox("Event Log (live)")
        log_layout = QVBoxLayout(log_group)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setFont(mono_font)
        self._log_text.setLineWrapMode(QTextEdit.NoWrap)
        log_layout.addWidget(self._log_text)

        # Clear button
        btn_layout = QHBoxLayout()
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self._clear_log)
        btn_layout.addStretch()
        btn_layout.addWidget(clear_btn)
        log_layout.addLayout(btn_layout)

        splitter.addWidget(log_group)

        # Splitter size hints
        splitter.setStretchFactor(0, 1)  # state
        splitter.setStretchFactor(1, 2)  # buffer
        splitter.setStretchFactor(2, 1)  # word
        splitter.setStretchFactor(3, 1)  # marker
        splitter.setStretchFactor(4, 1)  # selection
        splitter.setStretchFactor(5, 3)  # log

        main_layout.addWidget(splitter)

    def _connect_signals(self):
        """Connect internal signals to slots."""
        self._update_signal.connect(self._refresh_state)
        self._log_event_signal.connect(self._append_log_entry)

    # ------------------------------------------------------------------
    # Selection Poller Lifecycle
    # ------------------------------------------------------------------

    def _start_selection_poller(self):
        """Start background selection polling thread."""
        if self._selection_poller is not None:
            return
        if not hasattr(self._app, 'selection') or self._app.selection is None:
            return
        self._selection_poller = _SelectionPollerThread(self._app)
        self._selection_poller.selection_updated.connect(self._on_selection_updated)
        self._selection_poller.start()

    def _stop_selection_poller(self):
        """Stop background selection polling thread."""
        if self._selection_poller is not None:
            self._selection_poller.stop()
            self._selection_poller = None

    @pyqtSlot(str, int, float)
    def _on_selection_updated(self, text: str, owner_id: int, last_changed_at: float):
        """Handle selection update from poller thread (runs in GUI thread)."""
        # Truncate long text
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

    def show(self):
        """Override show to start selection poller."""
        super().show()
        self._start_selection_poller()

    def _subscribe_events(self):
        """Subscribe to EventBus events for live updates."""
        if self._event_bus is None:
            return

        # Key events
        self._event_bus.subscribe(EventType.KEY_PRESS, self._on_event)
        self._event_bus.subscribe(EventType.KEY_RELEASE, self._on_event)
        self._event_bus.subscribe(EventType.KEY_REPEAT, self._on_event)

        # Conversion lifecycle
        self._event_bus.subscribe(EventType.CONVERSION_START, self._on_event)
        self._event_bus.subscribe(EventType.CONVERSION_COMPLETE, self._on_event)
        self._event_bus.subscribe(EventType.CONVERSION_CANCELLED, self._on_event)

        # Others
        self._event_bus.subscribe(EventType.LAYOUT_CHANGED, self._on_event)
        self._event_bus.subscribe(EventType.DOUBLE_SHIFT, self._on_event)
        self._event_bus.subscribe(EventType.BACKSPACE_HOLD, self._on_event)

    def _unsubscribe_events(self):
        """Unsubscribe from EventBus to prevent leaks."""
        if self._event_bus is None:
            return

        for evt in [
            EventType.KEY_PRESS, EventType.KEY_RELEASE, EventType.KEY_REPEAT,
            EventType.CONVERSION_START, EventType.CONVERSION_COMPLETE, EventType.CONVERSION_CANCELLED,
            EventType.LAYOUT_CHANGED, EventType.DOUBLE_SHIFT, EventType.BACKSPACE_HOLD,
        ]:
            self._event_bus.unsubscribe(evt, self._on_event)

    def _start_timers(self):
        """Start periodic update timer for marker age."""
        self._age_timer = QTimer(self)
        self._age_timer.timeout.connect(self._update_marker_age)
        self._age_timer.start(1000)  # every second

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def _on_event(self, event: Event):
        """Handle EventBus event — emit signal for thread-safe GUI update."""
        # Format event for log
        ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
        evt_type = event.type.name
        data_str = self._format_event_data(event)

        # Emit signals (thread-safe)
        self._log_event_signal.emit(ts, evt_type, data_str)
        self._update_signal.emit()

    def _format_event_data(self, event: Event) -> str:
        """Format event data for log display."""
        data = event.data
        if data is None:
            return ""

        if event.type in (EventType.KEY_PRESS, EventType.KEY_RELEASE, EventType.KEY_REPEAT):
            # KeyEventData
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

    # ------------------------------------------------------------------
    # State Refresh (runs in GUI thread via signal)
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _refresh_state(self):
        """Refresh all state displays from app data."""
        if self._app is None or self._app.state_manager is None:
            return

        ctx = self._app.state_manager.context

        # Section 1: Current state
        self._state_label.setText(f"State: {ctx.state.name}")
        self._layout_label.setText(f"Layout: {ctx.current_layout}")
        self._chars_label.setText(f"Chars in buffer: {ctx.chars_in_buffer}")
        self._shift_label.setText(f"Shift pressed: {'yes' if ctx.shift_pressed else 'no'}")
        self._backspace_label.setText(
            f"Backspace hold: {'yes' if ctx.backspace_hold_active else 'no'} "
            f"(repeats: {ctx.backspace_repeats})"
        )
        self._sel_valid_label.setText(
            f"Selection valid: {'yes' if getattr(self._app, '_selection_valid', False) else 'no'}"
        )

        # Section 5: _prev_sel baseline
        prev_text = getattr(self._app, '_prev_sel_text', '')
        prev_owner = getattr(self._app, '_prev_sel_owner_id', 0)
        self._prev_sel_text_label.setText(
            f"Prev text: {prev_text!r}" if prev_text else "Prev text: (empty)"
        )
        self._prev_sel_owner_label.setText(
            f"Prev owner: {f'0x{prev_owner:08x}' if prev_owner else '-'}"
        )

        # Section 2: Event Buffer
        self._refresh_buffer_table(ctx.event_buffer)

        # Section 3: Last Word
        self._refresh_last_word()

        # Section 4: Auto Marker
        self._refresh_marker()

    def _refresh_buffer_table(self, event_buffer: list):
        """Update event buffer table."""
        self._buffer_table.setRowCount(len(event_buffer))

        summary_parts = []
        for i, ev in enumerate(event_buffer):
            code = getattr(ev, 'code', '?')
            shifted = getattr(ev, 'shifted', False)
            ch = keycode_to_char(code, shift=shifted) if isinstance(code, int) else '?'

            self._buffer_table.setItem(i, 0, QTableWidgetItem(str(i)))
            self._buffer_table.setItem(i, 1, QTableWidgetItem(str(code)))
            self._buffer_table.setItem(i, 2, QTableWidgetItem(ch or '-'))
            self._buffer_table.setItem(i, 3, QTableWidgetItem('Y' if shifted else 'N'))

            # Summary format: [16:Q]
            if ch:
                summary_parts.append(f"[{code}:{ch}]")
            else:
                summary_parts.append(f"[{code}:?]")

        if summary_parts:
            self._buffer_summary.setText("Buffer: " + " ".join(summary_parts))
        else:
            self._buffer_summary.setText("Buffer: (empty)")

    def _refresh_last_word(self):
        """Update last word display using app's _extract_last_word_events."""
        try:
            # Get current layout for proper character resolution
            current_layout = None
            if self._app.xkb:
                try:
                    current_layout = self._app.xkb.get_current_layout()
                except Exception:
                    pass

            word, word_events = self._app._extract_last_word_events(current_layout)

            if word:
                self._word_label.setText(f"Word: '{word}' ({len(word)} chars)")
                # Format events
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
        """Update auto marker display."""
        marker = getattr(self._app, '_last_auto_marker', None)

        if marker is None:
            self._marker_label.setText("No marker")
            self._marker_age_label.setText("Age: -")
            self._marker_label.setStyleSheet("")
        else:
            word = marker.get('word', '?')
            direction = marker.get('direction', '?')
            lang = marker.get('lang', '?')
            self._marker_label.setText(
                f"Word: '{word}'\n"
                f"Direction: {direction}\n"
                f"Lang: {lang}"
            )
            self._marker_label.setStyleSheet("color: #0077cc;")
            self._update_marker_age()

    @pyqtSlot()
    def _update_marker_age(self):
        """Update marker age display (called by timer)."""
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

    # ------------------------------------------------------------------
    # Event Log
    # ------------------------------------------------------------------

    @pyqtSlot(str, str, str)
    def _append_log_entry(self, timestamp: str, event_type: str, data: str):
        """Append entry to event log (thread-safe slot)."""
        # Color coding
        color = "#333333"
        if "KEY_PRESS" in event_type:
            color = "#006600"
        elif "KEY_RELEASE" in event_type:
            color = "#666666"
        elif "CONVERSION" in event_type:
            color = "#cc6600"
        elif "LAYOUT" in event_type:
            color = "#0066cc"
        elif "SHIFT" in event_type or "BACKSPACE" in event_type:
            color = "#cc0066"

        line = f"<span style='color:{color}'>[{timestamp}] {event_type}: {data}</span>"
        self._log_text.append(line)

        # Auto-scroll to bottom
        scrollbar = self._log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # Limit log size
        self._log_lines += 1
        if self._log_lines > self.MAX_LOG_LINES:
            # Trim old lines
            cursor = self._log_text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.movePosition(cursor.Down, cursor.KeepAnchor, 50)
            cursor.removeSelectedText()
            self._log_lines -= 50

    @pyqtSlot()
    def _clear_log(self):
        """Clear the event log."""
        self._log_text.clear()
        self._log_lines = 0

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        """Handle window close — cleanup subscriptions."""
        self._stop_selection_poller()
        self._age_timer.stop()
        self._unsubscribe_events()
        super().closeEvent(event)

    def cleanup(self):
        """Manual cleanup for external use."""
        self._stop_selection_poller()
        self._age_timer.stop()
        self._unsubscribe_events()
