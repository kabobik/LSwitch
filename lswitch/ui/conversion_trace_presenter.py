"""Qt-independent presentation helpers for conversion decision traces."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable

from lswitch.core.decision_trace import (
    DecisionOutcome,
    DecisionTrace,
    DecisionTraceStep,
    ExecutionOutcome,
    StepState,
)
from lswitch.i18n import t

Translate = Callable[..., str]

FILTER_ALL = "all"
FILTER_CONVERTED = "converted"
FILTER_KEPT = "kept"
FILTER_ERRORS = "errors"
TRACE_FILTERS = (
    FILTER_ALL,
    FILTER_CONVERTED,
    FILTER_KEPT,
    FILTER_ERRORS,
)


def _translated(
    key: str,
    fallback: str,
    translate: Translate,
    **kwargs,
) -> str:
    value = translate(key, **kwargs)
    return fallback.format(**kwargs) if value == key else value


def rule_label(rule_id: str, translate: Translate = t) -> str:
    """Return a localized rule label, falling back to the stable ID."""
    key = f"trace_rule_{rule_id.replace('.', '_')}"
    return _translated(key, rule_id, translate)


def rule_description(rule_id: str, translate: Translate = t) -> str:
    """Return an optional localized explanation for a stable rule ID."""
    key = f"trace_rule_{rule_id.replace('.', '_')}_description"
    value = translate(key)
    return "" if value == key else value


def outcome_label(value, translate: Translate = t) -> str:
    key = f"trace_outcome_{value.value}"
    return _translated(key, value.value.replace("_", " ").title(), translate)


def trigger_label(trace: DecisionTrace, translate: Translate = t) -> str:
    key = f"trace_trigger_{trace.trigger.value}"
    return _translated(
        key,
        trace.trigger.value.replace("_", " ").title(),
        translate,
    )


def step_state_label(state: StepState, translate: Translate = t) -> str:
    key = f"trace_step_{state.value}"
    return _translated(key, state.value.replace("_", " ").title(), translate)


def _step_marker(step: DecisionTraceStep) -> str:
    return {
        StepState.MATCHED: "✓",
        StepState.NOT_MATCHED: "○",
        StepState.SKIPPED: "—",
        StepState.SUCCEEDED: "✓",
        StepState.FAILED: "✕",
    }[step.state]


def _format_step(
    index: int,
    step: DecisionTraceStep,
    translate: Translate,
) -> list[str]:
    decisive = (
        " " + _translated("trace_decisive", "decisive", translate)
        if step.decisive
        else ""
    )
    lines = [
        f"  {index:>2}. {_step_marker(step)} {rule_label(step.rule_id, translate)} "
        f"[{step.rule_id}] — {step_state_label(step.state, translate)}{decisive}"
    ]
    description = rule_description(step.rule_id, translate)
    if description:
        lines.append(f"      {description}")
    for fact in step.facts:
        lines.append(f"      {fact.key}: {fact.value}")
    return lines


def format_trace(trace: DecisionTrace, translate: Translate = t) -> str:
    """Format a complete trace for the detail panel and explicit copy."""
    arrow_text = trace.original
    if trace.converted is not None:
        arrow_text = f"{arrow_text} → {trace.converted}"
    lines = [
        trigger_label(trace, translate).upper(),
        arrow_text,
        "",
        f"{_translated('trace_decision', 'Decision', translate)}: "
        f"{outcome_label(trace.decision, translate)}",
        f"{_translated('trace_execution', 'Execution', translate)}: "
        f"{outcome_label(trace.execution, translate)}",
    ]
    if trace.source_lang or trace.target_lang:
        direction = f"{trace.source_lang or '?'} → {trace.target_lang or '?'}"
        lines.append(
            f"{_translated('trace_direction', 'Direction', translate)}: "
            f"{direction.upper()}"
        )
    if trace.conversion_mode:
        lines.append(
            f"{_translated('trace_mode', 'Mode', translate)}: "
            f"{trace.conversion_mode}"
        )
    lines.extend(
        [
            f"{_translated('trace_duration', 'Duration', translate)}: "
            f"{trace.duration_ms:.2f} ms",
            f"{_translated('trace_correlation', 'Correlation', translate)}: "
            f"{trace.correlation_id}",
        ]
    )
    if trace.truncated:
        lines.append(
            _translated(
                "trace_truncated_notice",
                "Some captured text was truncated.",
                translate,
            )
        )

    if trace.attempts:
        lines.extend(
            [
                "",
                _translated("trace_decision_path", "Decision path", translate),
            ]
        )
        for attempt_index, attempt in enumerate(trace.attempts, 1):
            lines.append("")
            lines.append(
                _translated(
                    "trace_attempt",
                    'Attempt {number}: "{candidate}" — {outcome}',
                    translate,
                    number=attempt_index,
                    candidate=attempt.candidate,
                    outcome=outcome_label(attempt.outcome, translate),
                )
            )
            if attempt.converted_candidate is not None:
                lines.append(f"    {attempt.candidate} → {attempt.converted_candidate}")
            for step_index, step in enumerate(attempt.steps, 1):
                lines.extend(_format_step(step_index, step, translate))
            if attempt.steps and attempt.steps[-1].decisive:
                lines.append(
                    "    "
                    + _translated(
                        "trace_short_circuit_notice",
                        "Later rules were not evaluated after the decisive result.",
                        translate,
                    )
                )

    if trace.execution_steps:
        lines.extend(
            [
                "",
                _translated("trace_execution_path", "Execution path", translate),
            ]
        )
        for step_index, step in enumerate(trace.execution_steps, 1):
            lines.extend(_format_step(step_index, step, translate))

    return "\n".join(lines)


def format_trace_list_item(
    trace: DecisionTrace,
    *,
    related: bool = False,
    translate: Translate = t,
) -> str:
    """Format the compact two-line representation used in the master list."""
    value = trace.original
    if trace.converted is not None and trace.converted != trace.original:
        value = f"{value} → {trace.converted}"
    relationship = (
        " · " + _translated("trace_related", "related", translate)
        if related
        else ""
    )
    return (
        f"{trace.created_at.astimezone().strftime('%H:%M:%S')}  {value}\n"
        f"{outcome_label(trace.decision, translate)} · "
        f"{trigger_label(trace, translate)}{relationship}"
    )


def trace_matches(
    trace: DecisionTrace,
    filter_name: str = FILTER_ALL,
    query: str = "",
    translate: Translate = t,
) -> bool:
    """Return whether a trace is visible for the requested filter/search."""
    is_error = (
        trace.decision is DecisionOutcome.ERROR
        or trace.execution is ExecutionOutcome.FAILED
    )
    if filter_name == FILTER_CONVERTED:
        if trace.decision is not DecisionOutcome.CONVERT or is_error:
            return False
    elif filter_name == FILTER_KEPT:
        if trace.decision not in (DecisionOutcome.KEEP, DecisionOutcome.SKIP):
            return False
    elif filter_name == FILTER_ERRORS:
        if not is_error:
            return False
    elif filter_name != FILTER_ALL:
        return False

    normalized_query = query.casefold().strip()
    if not normalized_query:
        return True
    values = [
        trace.original,
        trace.converted or "",
        trace.trigger.value,
        trigger_label(trace, translate),
        trace.conversion_mode or "",
        trace.decision.value,
        trace.execution.value,
    ]
    for attempt in trace.attempts:
        values.extend((attempt.candidate, attempt.converted_candidate or ""))
        for step in attempt.steps:
            values.extend((step.rule_id, rule_label(step.rule_id, translate)))
    for step in trace.execution_steps:
        values.extend((step.rule_id, rule_label(step.rule_id, translate)))
    return any(normalized_query in str(value).casefold() for value in values)


class ConversionTraceViewModel:
    """Small identity-based model shared by the widget and unit tests."""

    def __init__(
        self,
        traces: Iterable[DecisionTrace] = (),
        *,
        max_entries: int = 200,
    ):
        self._traces: dict[int, DecisionTrace] = {}
        self._order: list[int] = []
        self._max_entries = max(1, int(max_entries))
        self.replace(traces)

    def replace(self, traces: Iterable[DecisionTrace]) -> None:
        self._traces.clear()
        self._order.clear()
        for trace in traces:
            self.upsert(trace)

    def upsert(self, trace: DecisionTrace) -> None:
        if trace.trace_id not in self._traces:
            self._order.append(trace.trace_id)
        self._traces[trace.trace_id] = trace
        while len(self._order) > self._max_entries:
            evicted_id = self._order.pop(0)
            self._traces.pop(evicted_id, None)

    def clear(self) -> None:
        self._traces.clear()
        self._order.clear()

    def get(self, trace_id: int | None) -> DecisionTrace | None:
        return self._traces.get(trace_id) if trace_id is not None else None

    def visible(
        self,
        filter_name: str = FILTER_ALL,
        query: str = "",
        translate: Translate = t,
    ) -> tuple[DecisionTrace, ...]:
        return tuple(
            trace
            for trace_id in reversed(self._order)
            if trace_matches(
                (trace := self._traces[trace_id]),
                filter_name,
                query,
                translate,
            )
        )

    def is_related(self, trace: DecisionTrace) -> bool:
        counts = Counter(item.correlation_id for item in self._traces.values())
        return counts[trace.correlation_id] > 1

    def __len__(self) -> int:
        return len(self._traces)
