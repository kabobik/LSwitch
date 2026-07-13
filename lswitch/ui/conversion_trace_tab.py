"""Independent Debug Monitor tab for structured conversion traces."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lswitch.core.decision_trace import (
    DecisionTrace,
    DecisionTraceClearedData,
)
from lswitch.core.events import Event, EventType
from lswitch.i18n import t
from lswitch.ui.conversion_trace_presenter import (
    FILTER_ALL,
    FILTER_CONVERTED,
    FILTER_ERRORS,
    FILTER_KEPT,
    ConversionTraceViewModel,
    format_trace,
    format_trace_list_item,
)

if TYPE_CHECKING:
    from lswitch.core.decision_trace import DecisionTraceRecorder
    from lswitch.core.event_bus import EventBus


class ConversionTraceTab(QWidget):
    """Master-detail trace history with a thread-safe EventBus bridge."""

    _trace_changed_signal = pyqtSignal(object)
    _trace_cleared_signal = pyqtSignal(object)

    def __init__(
        self,
        *,
        trace_recorder: "DecisionTraceRecorder | None",
        event_bus: "EventBus | None",
        translate: Callable[..., str] = t,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._recorder = trace_recorder
        self._event_bus = event_bus
        self._translate = translate
        self._model = ConversionTraceViewModel()
        self._enabled = bool(trace_recorder and trace_recorder.enabled)
        self._paused = False
        self._pending_count = 0
        self._selected_trace_id: int | None = None
        self._closed = False
        self._trace_event_handler = self._on_trace_event
        self._clear_event_handler = self._on_clear_event

        self._init_ui()
        self._trace_changed_signal.connect(self._apply_trace_change)
        self._trace_cleared_signal.connect(self._apply_trace_clear)
        self._subscribe()
        self._reload_snapshot()

    def _tr(self, key: str, fallback: str, **kwargs) -> str:
        value = self._translate(key, **kwargs)
        return fallback.format(**kwargs) if value == key else value

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()

        self._filter_combo = QComboBox()
        self._filter_combo.addItem(
            self._tr("trace_filter_all", "All"),
            FILTER_ALL,
        )
        self._filter_combo.addItem(
            self._tr("trace_filter_converted", "Converted"),
            FILTER_CONVERTED,
        )
        self._filter_combo.addItem(
            self._tr("trace_filter_kept", "Kept / skipped"),
            FILTER_KEPT,
        )
        self._filter_combo.addItem(
            self._tr("trace_filter_errors", "Errors"),
            FILTER_ERRORS,
        )
        self._filter_combo.setAccessibleName(
            self._tr("trace_filter_accessible", "Trace filter")
        )
        self._filter_combo.currentIndexChanged.connect(self._refresh_list)
        toolbar.addWidget(self._filter_combo)

        self._search = QLineEdit()
        self._search.setClearButtonEnabled(True)
        self._search.setPlaceholderText(
            self._tr("trace_search_placeholder", "Search traces…")
        )
        self._search.setAccessibleName(
            self._tr("trace_search_accessible", "Search conversion traces")
        )
        self._search.textChanged.connect(self._refresh_list)
        toolbar.addWidget(self._search, 1)

        self._pause_button = QPushButton(self._tr("trace_pause", "Pause"))
        self._pause_button.setCheckable(True)
        self._pause_button.setAccessibleName(
            self._tr("trace_pause_accessible", "Pause visual trace updates")
        )
        self._pause_button.toggled.connect(self._on_pause_toggled)
        toolbar.addWidget(self._pause_button)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        toolbar.addWidget(self._status_label)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._trace_list = QListWidget()
        self._trace_list.setAlternatingRowColors(True)
        self._trace_list.setWordWrap(True)
        self._trace_list.setAccessibleName(
            self._tr("trace_history_accessible", "Conversion trace history")
        )
        self._trace_list.currentItemChanged.connect(
            self._on_selection_changed
        )
        splitter.addWidget(self._trace_list)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        detail_font = QFont("Monospace", 9)
        detail_font.setStyleHint(QFont.StyleHint.Monospace)
        self._detail.setFont(detail_font)
        self._detail.setAccessibleName(
            self._tr("trace_detail_accessible", "Selected conversion trace")
        )
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self._clear_button = QPushButton(self._tr("trace_clear", "Clear"))
        self._clear_button.clicked.connect(self._clear_history)
        actions.addWidget(self._clear_button)
        actions.addStretch()
        self._copy_button = QPushButton(
            self._tr("trace_copy", "Copy trace")
        )
        self._copy_button.setToolTip(
            self._tr(
                "trace_copy_privacy_hint",
                "Copies the selected diagnostic trace, including captured text.",
            )
        )
        self._copy_button.clicked.connect(self._copy_selected)
        actions.addWidget(self._copy_button)
        layout.addLayout(actions)

    def _subscribe(self) -> None:
        if self._event_bus is None:
            return
        self._event_bus.subscribe(
            EventType.DECISION_TRACE_CHANGED,
            self._trace_event_handler,
        )
        self._event_bus.subscribe(
            EventType.DECISION_TRACE_CLEARED,
            self._clear_event_handler,
        )

    def _unsubscribe(self) -> None:
        if self._event_bus is None:
            return
        self._event_bus.unsubscribe(
            EventType.DECISION_TRACE_CHANGED,
            self._trace_event_handler,
        )
        self._event_bus.unsubscribe(
            EventType.DECISION_TRACE_CLEARED,
            self._clear_event_handler,
        )

    def _on_trace_event(self, event: Event) -> None:
        if not self._closed and isinstance(event.data, DecisionTrace):
            self._trace_changed_signal.emit(event.data)

    def _on_clear_event(self, event: Event) -> None:
        if not self._closed and isinstance(event.data, DecisionTraceClearedData):
            self._trace_cleared_signal.emit(event.data)

    @pyqtSlot(object)
    def _apply_trace_change(self, trace: DecisionTrace) -> None:
        if self._paused:
            self._pending_count += 1
            self._update_status()
            return
        self._model.upsert(trace)
        self._refresh_list()

    @pyqtSlot(object)
    def _apply_trace_clear(self, data: DecisionTraceClearedData) -> None:
        self._enabled = data.enabled
        self._pending_count = 0
        self._model.clear()
        self._selected_trace_id = None
        self._refresh_list()

    def _reload_snapshot(self) -> None:
        self._enabled = bool(self._recorder and self._recorder.enabled)
        traces = self._recorder.snapshot() if self._enabled else ()
        self._model.replace(traces)
        self._refresh_list()

    def _current_filter(self) -> str:
        return self._filter_combo.currentData() or FILTER_ALL

    def _current_item_trace_id(self) -> int | None:
        item = self._trace_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    @pyqtSlot()
    def _refresh_list(self, _value=None) -> None:
        preferred_id = self._current_item_trace_id()
        if preferred_id is None:
            preferred_id = self._selected_trace_id
        visible = self._model.visible(
            self._current_filter(),
            self._search.text(),
            self._translate,
        )

        self._trace_list.blockSignals(True)
        self._trace_list.clear()
        selected_row = -1
        for row, trace in enumerate(visible):
            item = QListWidgetItem(
                format_trace_list_item(
                    trace,
                    related=self._model.is_related(trace),
                    translate=self._translate,
                )
            )
            item.setData(Qt.ItemDataRole.UserRole, trace.trace_id)
            item.setToolTip(format_trace(trace, self._translate))
            self._trace_list.addItem(item)
            if trace.trace_id == preferred_id:
                selected_row = row
        if selected_row < 0 and visible:
            selected_row = 0
        if selected_row >= 0:
            self._trace_list.setCurrentRow(selected_row)
            self._selected_trace_id = visible[selected_row].trace_id
        else:
            self._selected_trace_id = None
        self._trace_list.blockSignals(False)

        self._render_selected()
        self._update_status(visible_count=len(visible))

    def _on_selection_changed(self, current, _previous) -> None:
        self._selected_trace_id = (
            current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        )
        self._render_selected()

    def _render_selected(self) -> None:
        trace = self._model.get(self._selected_trace_id)
        self._detail.setPlainText(
            format_trace(trace, self._translate) if trace is not None else ""
        )
        self._copy_button.setEnabled(trace is not None)

    def _update_status(self, *, visible_count: int | None = None) -> None:
        if not self._enabled:
            text = self._tr(
                "trace_disabled",
                "Tracing is disabled. Enable effective debug to collect data.",
            )
        elif self._paused:
            text = self._tr(
                "trace_paused_count",
                "Paused · {count} pending updates",
                count=self._pending_count,
            )
        elif len(self._model) == 0:
            text = self._tr(
                "trace_empty",
                "No conversion traces have been collected yet.",
            )
        elif visible_count == 0:
            text = self._tr("trace_no_matches", "No matching traces.")
        else:
            text = self._tr(
                "trace_entry_count",
                "{count} traces",
                count=len(self._model),
            )
        self._status_label.setText(text)
        self._clear_button.setEnabled(self._enabled and len(self._model) > 0)

    def _on_pause_toggled(self, paused: bool) -> None:
        self._paused = paused
        self._pause_button.setText(
            self._tr("trace_resume", "Resume")
            if paused
            else self._tr("trace_pause", "Pause")
        )
        if not paused:
            self._pending_count = 0
            self._reload_snapshot()
        else:
            self._update_status()

    def _clear_history(self) -> None:
        if self._recorder is not None:
            self._recorder.clear()

    def _copy_selected(self) -> None:
        trace = self._model.get(self._selected_trace_id)
        if trace is None:
            return
        QApplication.clipboard().setText(format_trace(trace, self._translate))

    def cleanup(self) -> None:
        """Detach from EventBus without changing recorder lifecycle."""
        if self._closed:
            return
        self._closed = True
        self._unsubscribe()

    def closeEvent(self, event) -> None:
        self.cleanup()
        super().closeEvent(event)
