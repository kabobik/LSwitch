"""Tests for the Qt-independent conversion trace presentation model."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from lswitch.core.decision_trace import (
    DecisionAttempt,
    DecisionOutcome,
    DecisionTrace,
    DecisionTraceStep,
    ExecutionOutcome,
    StepState,
    TraceFact,
    TraceTrigger,
)
from lswitch.ui.conversion_trace_presenter import (
    FILTER_CONVERTED,
    FILTER_ERRORS,
    FILTER_KEPT,
    ConversionTraceViewModel,
    format_trace,
    trace_matches,
)


def _trace(
    trace_id: int,
    *,
    decision: DecisionOutcome = DecisionOutcome.CONVERT,
    execution: ExecutionOutcome = ExecutionOutcome.SUCCEEDED,
    original: str = "ghbdtn",
    correlation_id: int | None = None,
) -> DecisionTrace:
    step = DecisionTraceStep(
        "unknown.rule",
        StepState.MATCHED,
        decisive=True,
        facts=(TraceFact("score", 12.5),),
    )
    return DecisionTrace(
        trace_id=trace_id,
        correlation_id=correlation_id or trace_id,
        created_at=datetime(2026, 7, 13, 11, 18, 35, tzinfo=timezone.utc),
        trigger=TraceTrigger.SPACE_AUTO,
        original=original,
        converted="привет" if decision is DecisionOutcome.CONVERT else None,
        source_lang="en",
        target_lang="ru",
        decision=decision,
        execution=execution,
        attempts=(
            DecisionAttempt(
                candidate=original,
                converted_candidate="привет",
                source_lang="en",
                target_lang="ru",
                outcome=decision,
                steps=(step,),
            ),
        ),
        execution_steps=(
            DecisionTraceStep("execution.success", StepState.SUCCEEDED),
        ),
        duration_ms=1.25,
    )


def test_formatter_keeps_unknown_rule_id_and_facts_visible():
    rendered = format_trace(_trace(1), translate=lambda key, **kwargs: key)

    assert "unknown.rule" in rendered
    assert "score: 12.5" in rendered
    assert "decisive" in rendered
    assert "Decision: Convert" in rendered
    assert "Execution: Succeeded" in rendered


def test_filters_separate_successful_conversions_keeps_and_errors():
    converted = _trace(1)
    kept = _trace(2, decision=DecisionOutcome.KEEP)
    failed = _trace(3, execution=ExecutionOutcome.FAILED)

    assert trace_matches(converted, FILTER_CONVERTED)
    assert not trace_matches(failed, FILTER_CONVERTED)
    assert trace_matches(kept, FILTER_KEPT)
    assert trace_matches(failed, FILTER_ERRORS)


def test_search_covers_text_rule_ids_and_localized_rule_labels():
    trace = _trace(1)

    def translate(key, **kwargs):
        if key == "trace_rule_unknown_rule":
            return "Localized evidence"
        return key

    assert trace_matches(trace, query="привет")
    assert trace_matches(trace, query="unknown.rule")
    assert trace_matches(trace, query="localized evidence", translate=translate)
    assert not trace_matches(trace, query="missing")


def test_view_model_updates_same_identity_and_keeps_newest_first():
    model = ConversionTraceViewModel((_trace(1), _trace(2)))
    updated = replace(_trace(1), original="updated")

    model.upsert(updated)

    assert len(model) == 2
    assert model.get(1).original == "updated"
    assert tuple(item.trace_id for item in model.visible()) == (2, 1)


def test_view_model_is_bounded_and_marks_related_flows():
    first = _trace(1, correlation_id=42)
    related = replace(
        _trace(2, correlation_id=42),
        trigger=TraceTrigger.MID_WORD,
    )
    model = ConversionTraceViewModel((first, related), max_entries=2)

    assert model.is_related(first)
    assert model.is_related(related)

    model.upsert(_trace(3))

    assert model.get(1) is None
    assert tuple(item.trace_id for item in model.visible()) == (3, 2)
