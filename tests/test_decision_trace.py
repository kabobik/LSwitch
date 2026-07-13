"""Tests for immutable conversion traces and their bounded recorder."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from lswitch.core.decision_trace import (
    MAX_TRACE_TEXT_LENGTH,
    DecisionAttempt,
    DecisionOutcome,
    DecisionTrace,
    DecisionTraceRecorder,
    DecisionTraceStep,
    ExecutionOutcome,
    StepState,
    TraceFact,
    TraceLifecycle,
    TraceTrigger,
)
from lswitch.core.event_bus import EventBus
from lswitch.core.events import EventType


def _trace(number: int) -> DecisionTrace:
    return DecisionTrace(
        correlation_id=number,
        trigger=TraceTrigger.SPACE_AUTO,
        original=f"word-{number}",
        decision=DecisionOutcome.KEEP,
    )


def test_trace_owns_immutable_nested_values():
    facts = [TraceFact("count", 2)]
    steps = [
        DecisionTraceStep(
            "auto.source_dictionary.match",
            StepState.MATCHED,
            decisive=True,
            facts=facts,
        )
    ]
    attempts = [
        DecisionAttempt(
            candidate="hello",
            outcome=DecisionOutcome.KEEP,
            steps=steps,
        )
    ]

    trace = DecisionTrace(
        correlation_id=1,
        trigger=TraceTrigger.SPACE_AUTO,
        original="hello",
        decision=DecisionOutcome.KEEP,
        attempts=attempts,
    )
    facts.append(TraceFact("changed", True))
    steps.clear()
    attempts.clear()

    assert trace.attempts[0].steps[0].facts == (TraceFact("count", 2),)
    with pytest.raises(FrozenInstanceError):
        trace.original = "changed"


def test_trace_rejects_mutable_fact_values():
    with pytest.raises(TypeError):
        TraceFact("bad", {"mutable": True})


def test_trace_truncates_long_candidate_and_marks_record():
    candidate = "x" * (MAX_TRACE_TEXT_LENGTH + 20)
    attempt = DecisionAttempt(
        candidate=candidate,
        outcome=DecisionOutcome.SKIP,
    )
    trace = DecisionTrace(
        correlation_id=1,
        trigger=TraceTrigger.MANUAL,
        original=candidate,
        decision=DecisionOutcome.SKIP,
        attempts=(attempt,),
    )

    assert len(trace.original) == MAX_TRACE_TEXT_LENGTH
    assert len(trace.attempts[0].candidate) == MAX_TRACE_TEXT_LENGTH
    assert trace.truncated is True


def test_naive_created_at_is_normalized_to_utc():
    trace = DecisionTrace(
        correlation_id=1,
        trigger=TraceTrigger.MANUAL,
        original="text",
        decision=DecisionOutcome.SKIP,
        created_at=datetime(2026, 7, 13, 12, 0),
    )

    assert trace.created_at.utcoffset() is not None


def test_disabled_recorder_is_a_no_op():
    recorder = DecisionTraceRecorder(enabled=False)

    assert recorder.record(_trace(1)) is None
    assert recorder.snapshot() == ()


def test_recorder_assigns_ids_and_evicts_oldest_entry():
    recorder = DecisionTraceRecorder(enabled=True, max_entries=2)

    first = recorder.record(_trace(1))
    second = recorder.record(_trace(2))
    third = recorder.record(_trace(3))

    assert first is not None
    assert second is not None
    assert third is not None
    assert [trace.trace_id for trace in recorder.snapshot()] == [
        second.trace_id,
        third.trace_id,
    ]


def test_recorder_publishes_changed_and_cleared_events():
    bus = EventBus()
    changed = []
    cleared = []
    bus.subscribe(EventType.DECISION_TRACE_CHANGED, changed.append)
    bus.subscribe(EventType.DECISION_TRACE_CLEARED, cleared.append)
    recorder = DecisionTraceRecorder(bus, enabled=True)

    stored = recorder.record(_trace(1))
    recorder.clear()

    assert changed[0].data == stored
    assert cleared[0].data.enabled is True


def test_reconfigure_false_clears_history_and_true_notifies_state():
    bus = EventBus()
    cleared = []
    bus.subscribe(EventType.DECISION_TRACE_CLEARED, cleared.append)
    recorder = DecisionTraceRecorder(bus, enabled=True)
    recorder.record(_trace(1))

    recorder.reconfigure(enabled=False)
    recorder.reconfigure(enabled=True)

    assert recorder.snapshot() == ()
    assert [event.data.enabled for event in cleared] == [False, True]


def test_upsert_attempt_replaces_one_mid_word_trace():
    recorder = DecisionTraceRecorder(enabled=True)
    first_attempt = DecisionAttempt(
        candidate="ghb",
        outcome=DecisionOutcome.KEEP,
    )
    final_attempt = DecisionAttempt(
        candidate="ghbd",
        converted_candidate="прив",
        source_lang="en",
        target_lang="ru",
        outcome=DecisionOutcome.CONVERT,
        duration_ms=0.5,
    )

    first = recorder.upsert_attempt(7, TraceTrigger.MID_WORD, first_attempt)
    updated = recorder.upsert_attempt(7, TraceTrigger.MID_WORD, final_attempt)
    finalized = recorder.finalize_session(
        7,
        TraceTrigger.MID_WORD,
        execution=ExecutionOutcome.SUCCEEDED,
        converted="прив",
    )

    assert first is not None
    assert updated is not None
    assert finalized is not None
    assert first.trace_id == updated.trace_id == finalized.trace_id
    assert len(recorder.snapshot()) == 1
    assert finalized.attempts == (first_attempt, final_attempt)
    assert finalized.execution is ExecutionOutcome.SUCCEEDED
    assert first.lifecycle is TraceLifecycle.ACTIVE
    assert updated.lifecycle is TraceLifecycle.ACTIVE
    assert finalized.lifecycle is TraceLifecycle.FINALIZED


def test_close_session_starts_new_trace_for_same_correlation():
    bus = EventBus()
    changed = []
    bus.subscribe(EventType.DECISION_TRACE_CHANGED, changed.append)
    recorder = DecisionTraceRecorder(bus, enabled=True)
    attempt = DecisionAttempt(
        candidate="ghbd",
        outcome=DecisionOutcome.KEEP,
    )

    first = recorder.upsert_attempt(9, TraceTrigger.MID_WORD, attempt)
    recorder.close_session(9)
    second = recorder.upsert_attempt(9, TraceTrigger.MID_WORD, attempt)

    assert first is not None
    assert second is not None
    assert first.trace_id != second.trace_id
    assert recorder.snapshot()[0].lifecycle is TraceLifecycle.FINALIZED
    assert recorder.snapshot()[1].lifecycle is TraceLifecycle.ACTIVE
    assert changed[-2].data.lifecycle is TraceLifecycle.FINALIZED


def test_finalize_session_starts_related_trace_for_later_segment():
    recorder = DecisionTraceRecorder(enabled=True)
    attempt = DecisionAttempt(
        candidate="рудд",
        converted_candidate="hell",
        outcome=DecisionOutcome.CONVERT,
    )

    converted = recorder.upsert_attempt(12, TraceTrigger.MID_WORD, attempt)
    recorder.finalize_session(
        12,
        TraceTrigger.MID_WORD,
        execution=ExecutionOutcome.SUCCEEDED,
    )
    continuation = recorder.upsert_attempt(
        12,
        TraceTrigger.MID_WORD,
        DecisionAttempt(candidate="o", outcome=DecisionOutcome.KEEP),
    )

    assert converted is not None
    assert continuation is not None
    assert continuation.trace_id != converted.trace_id
    assert [trace.correlation_id for trace in recorder.snapshot()] == [12, 12]


def test_recorder_is_safe_for_parallel_writers():
    recorder = DecisionTraceRecorder(enabled=True, max_entries=500)

    def record_range(start: int) -> None:
        for number in range(start, start + 100):
            recorder.record(_trace(number))

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(record_range, (0, 100, 200, 300)))

    snapshot = recorder.snapshot()
    ids = [trace.trace_id for trace in snapshot]
    assert len(snapshot) == 400
    assert len(set(ids)) == 400
    assert ids == sorted(ids)


def test_event_handler_failure_does_not_break_recording():
    class BrokenBus:
        def publish(self, event) -> None:
            raise RuntimeError("broken")

    recorder = DecisionTraceRecorder(BrokenBus(), enabled=True)

    stored = recorder.record(_trace(1))

    assert stored is not None
    assert recorder.snapshot() == (stored,)
