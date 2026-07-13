"""Offscreen Qt tests for the independent conversion trace tab."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from lswitch.core.decision_trace import (
    DecisionAttempt,
    DecisionOutcome,
    DecisionTrace,
    DecisionTraceRecorder,
    TraceTrigger,
)
from lswitch.core.event_bus import EventBus
from lswitch.core.events import EventType
from lswitch.core.states import State, StateContext
from lswitch.ui.conversion_trace_tab import ConversionTraceTab
from lswitch.ui.debug_monitor import DebugMonitorWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _record(recorder, correlation_id, original="ghbdtn"):
    return recorder.record(
        DecisionTrace(
            correlation_id=correlation_id,
            trigger=TraceTrigger.SPACE_AUTO,
            original=original,
            converted="привет",
            decision=DecisionOutcome.CONVERT,
        )
    )


def _tab():
    event_bus = EventBus()
    recorder = DecisionTraceRecorder(event_bus, enabled=True)
    return event_bus, recorder, ConversionTraceTab(
        trace_recorder=recorder,
        event_bus=event_bus,
    )


def test_backlog_is_loaded_and_cleanup_removes_subscriptions(qapp):
    event_bus = EventBus()
    recorder = DecisionTraceRecorder(event_bus, enabled=True)
    _record(recorder, 1)

    tab = ConversionTraceTab(
        trace_recorder=recorder,
        event_bus=event_bus,
    )
    qapp.processEvents()

    assert tab._trace_list.count() == 1
    assert "ghbdtn" in tab._detail.toPlainText()
    assert len(event_bus._handlers[EventType.DECISION_TRACE_CHANGED]) == 1

    tab.cleanup()

    assert event_bus._handlers[EventType.DECISION_TRACE_CHANGED] == []
    assert event_bus._handlers[EventType.DECISION_TRACE_CLEARED] == []


def test_pause_freezes_view_and_resume_reloads_snapshot(qapp):
    _event_bus, recorder, tab = _tab()
    _record(recorder, 1)
    qapp.processEvents()
    assert tab._trace_list.count() == 1

    tab._pause_button.setChecked(True)
    _record(recorder, 2, "world")
    qapp.processEvents()

    assert tab._trace_list.count() == 1
    assert tab._pending_count == 1

    tab._pause_button.setChecked(False)
    qapp.processEvents()

    assert tab._trace_list.count() == 2
    assert "world" in tab._trace_list.item(0).text()
    tab.cleanup()


def test_same_midword_trace_id_is_updated_in_place(qapp):
    _event_bus, recorder, tab = _tab()
    recorder.upsert_attempt(
        7,
        TraceTrigger.MID_WORD,
        DecisionAttempt(candidate="gh", outcome=DecisionOutcome.KEEP),
    )
    qapp.processEvents()
    recorder.upsert_attempt(
        7,
        TraceTrigger.MID_WORD,
        DecisionAttempt(candidate="ghb", outcome=DecisionOutcome.KEEP),
    )
    qapp.processEvents()

    assert tab._trace_list.count() == 1
    assert "ghb" in tab._trace_list.item(0).text()
    assert "Attempt 2" in tab._detail.toPlainText()
    tab.cleanup()


def test_filter_search_clear_and_copy_do_not_mutate_unintentionally(qapp):
    _event_bus, recorder, tab = _tab()
    stored = _record(recorder, 1)
    recorder.record(
        DecisionTrace(
            correlation_id=2,
            trigger=TraceTrigger.SPACE_AUTO,
            original="hello",
            decision=DecisionOutcome.KEEP,
        )
    )
    qapp.processEvents()
    assert len(recorder.snapshot()) == 2

    tab._search.setText("ghbdtn")
    qapp.processEvents()
    assert tab._trace_list.count() == 1
    assert len(recorder.snapshot()) == 2

    tab._copy_button.click()
    assert stored.original in QApplication.clipboard().text()

    tab._clear_button.click()
    qapp.processEvents()
    assert recorder.snapshot() == ()
    assert tab._trace_list.count() == 0
    assert tab._detail.toPlainText() == ""
    tab.cleanup()


def test_disabling_recorder_clears_open_tab(qapp):
    _event_bus, recorder, tab = _tab()
    _record(recorder, 1)
    qapp.processEvents()

    recorder.reconfigure(enabled=False)
    qapp.processEvents()

    assert tab._trace_list.count() == 0
    assert "disabled" in tab._status_label.text().lower()
    assert not tab._clear_button.isEnabled()
    tab.cleanup()


def test_debug_monitor_wraps_legacy_state_in_second_tab(qapp):
    event_bus = EventBus()
    recorder = DecisionTraceRecorder(event_bus, enabled=True)
    context = StateContext()
    context.state = State.IDLE
    app = SimpleNamespace(
        state_manager=SimpleNamespace(context=context),
        trace_recorder=recorder,
        conversion_runtime=SimpleNamespace(
            extract_last_word=lambda _layout: ("", []),
        ),
        auto_conversion_session=SimpleNamespace(last_marker=None),
        xkb=None,
        _selection_valid=False,
        _prev_sel_text="",
        _prev_sel_owner_id=0,
    )

    window = DebugMonitorWindow(
        app=app,
        event_bus=event_bus,
        trace_recorder=recorder,
    )
    qapp.processEvents()

    assert window._tabs.count() == 2
    assert window._tabs.currentIndex() == 0
    assert window._tabs.widget(0) is window._conversion_trace_tab
    assert window._tabs.widget(1) is window._state_tab

    window.cleanup()
