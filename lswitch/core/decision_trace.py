"""Structured conversion-decision traces for the debug inspector."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, TypeAlias

from lswitch.core.events import Event, EventType

if TYPE_CHECKING:
    from lswitch.core.event_bus import EventBus

logger = logging.getLogger(__name__)

MAX_TRACE_TEXT_LENGTH = 256
TraceFactValue: TypeAlias = str | int | float | bool | None


class TraceTrigger(str, Enum):
    """Conversion flow which evaluated a candidate."""

    SPACE_AUTO = "space_auto"
    MID_WORD = "mid_word"
    MANUAL = "manual"
    UNDO = "undo"


class DecisionOutcome(str, Enum):
    """Algorithm-level result, independent from execution."""

    CONVERT = "convert"
    KEEP = "keep"
    SKIP = "skip"
    ERROR = "error"


class ExecutionOutcome(str, Enum):
    """Result of applying an already made decision."""

    NOT_STARTED = "not_started"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    FAILED = "failed"


class StepState(str, Enum):
    """Result of one rule or execution step."""

    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    SKIPPED = "skipped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _limited_text(value: str | None) -> tuple[str | None, bool]:
    if value is None or len(value) <= MAX_TRACE_TEXT_LENGTH:
        return value, False
    return value[: MAX_TRACE_TEXT_LENGTH - 1] + "…", True


@dataclass(frozen=True)
class TraceFact:
    """Immutable key/value captured when a rule was evaluated."""

    key: str
    value: TraceFactValue

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key:
            raise ValueError("trace fact key must be a non-empty string")
        if not isinstance(self.value, (str, int, float, bool, type(None))):
            raise TypeError("trace fact values must be scalar")
        if isinstance(self.value, str):
            value, _ = _limited_text(self.value)
            object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class DecisionTraceStep:
    """One stable rule result in decision or execution order."""

    rule_id: str
    state: StepState
    decisive: bool = False
    facts: tuple[TraceFact, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or not self.rule_id:
            raise ValueError("trace rule_id must be a non-empty string")
        object.__setattr__(self, "facts", tuple(self.facts))


@dataclass(frozen=True)
class DecisionAttempt:
    """One detector evaluation; mid-word traces contain several attempts."""

    candidate: str
    outcome: DecisionOutcome
    converted_candidate: str | None = None
    source_lang: str | None = None
    target_lang: str | None = None
    steps: tuple[DecisionTraceStep, ...] = ()
    duration_ms: float = 0.0
    truncated: bool = False

    def __post_init__(self) -> None:
        candidate, candidate_truncated = _limited_text(self.candidate)
        converted, converted_truncated = _limited_text(self.converted_candidate)
        object.__setattr__(self, "candidate", candidate or "")
        object.__setattr__(self, "converted_candidate", converted)
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "duration_ms", max(0.0, float(self.duration_ms)))
        object.__setattr__(
            self,
            "truncated",
            bool(self.truncated or candidate_truncated or converted_truncated),
        )


@dataclass(frozen=True)
class DecisionTrace:
    """Complete immutable diagnostic record shown by the debug inspector."""

    correlation_id: int
    trigger: TraceTrigger
    original: str
    decision: DecisionOutcome
    trace_id: int = 0
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    converted: str | None = None
    source_lang: str | None = None
    target_lang: str | None = None
    execution: ExecutionOutcome = ExecutionOutcome.NOT_STARTED
    conversion_mode: str | None = None
    attempts: tuple[DecisionAttempt, ...] = ()
    execution_steps: tuple[DecisionTraceStep, ...] = ()
    duration_ms: float = 0.0
    truncated: bool = False

    def __post_init__(self) -> None:
        original, original_truncated = _limited_text(self.original)
        converted, converted_truncated = _limited_text(self.converted)
        attempts = tuple(self.attempts)
        object.__setattr__(self, "original", original or "")
        object.__setattr__(self, "converted", converted)
        object.__setattr__(self, "attempts", attempts)
        object.__setattr__(self, "execution_steps", tuple(self.execution_steps))
        object.__setattr__(self, "duration_ms", max(0.0, float(self.duration_ms)))
        object.__setattr__(
            self,
            "truncated",
            bool(
                self.truncated
                or original_truncated
                or converted_truncated
                or any(attempt.truncated for attempt in attempts)
            ),
        )
        if self.created_at.tzinfo is None:
            object.__setattr__(
                self,
                "created_at",
                self.created_at.replace(tzinfo=timezone.utc),
            )


@dataclass(frozen=True)
class DecisionTraceClearedData:
    """Payload for a history clear or recorder enabled-state change."""

    enabled: bool


class DecisionTraceRecorder:
    """Thread-safe bounded in-memory store for conversion traces."""

    def __init__(
        self,
        event_bus: "EventBus | None" = None,
        *,
        enabled: bool = False,
        max_entries: int = 200,
    ):
        self._event_bus = event_bus
        self._enabled = bool(enabled)
        self._max_entries = max(1, int(max_entries))
        self._traces: deque[DecisionTrace] = deque(maxlen=self._max_entries)
        self._session_trace_ids: dict[tuple[int, TraceTrigger], int] = {}
        self._next_trace_id = 1
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def reconfigure(self, *, enabled: bool) -> None:
        """Change recording state; disabling also removes sensitive history."""
        enabled = bool(enabled)
        with self._lock:
            if enabled == self._enabled:
                return
            self._enabled = enabled
            self._traces.clear()
            self._session_trace_ids.clear()
        self._publish_cleared(enabled)

    def record(self, trace: DecisionTrace) -> DecisionTrace | None:
        """Append a one-shot trace and assign its process-local ID."""
        with self._lock:
            if not self._enabled:
                return None
            stored = replace(trace, trace_id=self._next_trace_id)
            self._next_trace_id += 1
            self._append_locked(stored)
        self._publish_changed(stored)
        return stored

    def upsert_attempt(
        self,
        correlation_id: int,
        trigger: TraceTrigger,
        attempt: DecisionAttempt,
    ) -> DecisionTrace | None:
        """Append an attempt to the active trace for a word session."""
        key = (int(correlation_id), trigger)
        with self._lock:
            if not self._enabled:
                return None
            trace_id = self._session_trace_ids.get(key)
            index = self._find_index_locked(trace_id) if trace_id else None
            if index is None:
                stored = DecisionTrace(
                    trace_id=self._next_trace_id,
                    correlation_id=key[0],
                    trigger=trigger,
                    original=attempt.candidate,
                    converted=attempt.converted_candidate,
                    source_lang=attempt.source_lang,
                    target_lang=attempt.target_lang,
                    decision=attempt.outcome,
                    attempts=(attempt,),
                    duration_ms=attempt.duration_ms,
                    truncated=attempt.truncated,
                )
                self._next_trace_id += 1
                self._append_locked(stored)
                self._session_trace_ids[key] = stored.trace_id
            else:
                current = self._traces[index]
                stored = replace(
                    current,
                    original=attempt.candidate,
                    converted=attempt.converted_candidate,
                    source_lang=attempt.source_lang,
                    target_lang=attempt.target_lang,
                    decision=attempt.outcome,
                    attempts=current.attempts + (attempt,),
                    duration_ms=current.duration_ms + attempt.duration_ms,
                    truncated=current.truncated or attempt.truncated,
                )
                self._traces[index] = stored
        self._publish_changed(stored)
        return stored

    def finalize_session(
        self,
        correlation_id: int,
        trigger: TraceTrigger,
        *,
        decision: DecisionOutcome | None = None,
        execution: ExecutionOutcome = ExecutionOutcome.NOT_STARTED,
        converted: str | None = None,
        conversion_mode: str | None = None,
        execution_steps: tuple[DecisionTraceStep, ...] = (),
        duration_ms: float = 0.0,
    ) -> DecisionTrace | None:
        """Finalize an active trace without closing other flow traces."""
        key = (int(correlation_id), trigger)
        with self._lock:
            if not self._enabled:
                return None
            trace_id = self._session_trace_ids.get(key)
            index = self._find_index_locked(trace_id) if trace_id else None
            if index is None:
                return None
            current = self._traces[index]
            stored = replace(
                current,
                decision=decision or current.decision,
                execution=execution,
                converted=converted if converted is not None else current.converted,
                conversion_mode=conversion_mode or current.conversion_mode,
                execution_steps=tuple(execution_steps),
                duration_ms=current.duration_ms + max(0.0, float(duration_ms)),
            )
            self._traces[index] = stored
        self._publish_changed(stored)
        return stored

    def close_session(self, correlation_id: int) -> None:
        """Stop future updates for all traces associated with a word."""
        correlation_id = int(correlation_id)
        with self._lock:
            keys = [
                key
                for key in self._session_trace_ids
                if key[0] == correlation_id
            ]
            for key in keys:
                self._session_trace_ids.pop(key, None)

    def snapshot(self) -> tuple[DecisionTrace, ...]:
        """Return an oldest-to-newest immutable history snapshot."""
        with self._lock:
            return tuple(self._traces)

    def clear(self) -> None:
        """Clear history without changing the enabled state."""
        with self._lock:
            self._traces.clear()
            self._session_trace_ids.clear()
            enabled = self._enabled
        self._publish_cleared(enabled)

    def _append_locked(self, trace: DecisionTrace) -> None:
        evicted_id = (
            self._traces[0].trace_id
            if len(self._traces) == self._max_entries
            else None
        )
        self._traces.append(trace)
        if evicted_id is not None:
            keys = [
                key
                for key, trace_id in self._session_trace_ids.items()
                if trace_id == evicted_id
            ]
            for key in keys:
                self._session_trace_ids.pop(key, None)

    def _find_index_locked(self, trace_id: int | None) -> int | None:
        if trace_id is None:
            return None
        for index, trace in enumerate(self._traces):
            if trace.trace_id == trace_id:
                return index
        return None

    def _publish_changed(self, trace: DecisionTrace) -> None:
        self._publish(EventType.DECISION_TRACE_CHANGED, trace)

    def _publish_cleared(self, enabled: bool) -> None:
        self._publish(
            EventType.DECISION_TRACE_CLEARED,
            DecisionTraceClearedData(enabled=enabled),
        )

    def _publish(self, event_type: EventType, data) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(
                Event(type=event_type, data=data, timestamp=time.time())
            )
        except Exception:
            logger.exception("Failed to publish decision trace event")
