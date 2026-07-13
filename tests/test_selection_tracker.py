"""Tests for selection freshness state tracker."""

from __future__ import annotations

from lswitch.core.selection_tracker import SelectionFreshnessTracker


def test_valid_generation_increments_only_on_false_to_true():
    tracker = SelectionFreshnessTracker()

    tracker.set_valid(True)
    tracker.set_valid(True)
    tracker.set_valid(False)
    tracker.set_valid(True)

    assert tracker.generation == 2


def test_release_selection_initializes_baseline_without_fresh():
    tracker = SelectionFreshnessTracker()

    result = tracker.on_release_selection("hello", 42)

    assert result == "initial"
    assert tracker.valid is False
    assert tracker.prev_text == "hello"
    assert tracker.prev_owner_id == 42
    assert tracker.baseline_initialized is True


def test_release_selection_marks_fresh_on_text_change():
    tracker = SelectionFreshnessTracker(
        prev_text="old",
        prev_owner_id=1,
        baseline_initialized=True,
    )

    result = tracker.on_release_selection("new", 1)

    assert result == "fresh"
    assert tracker.valid is True
    assert tracker.generation == 1
    assert tracker.prev_text == "new"


def test_release_empty_selection_resets_fresh_and_repeat():
    tracker = SelectionFreshnessTracker(valid=True, repeat_valid=True)

    result = tracker.on_release_selection("", 0)

    assert result == "empty"
    assert tracker.valid is False
    assert tracker.repeat_valid is False


def test_click_passive_selection_marks_fresh_on_owner_change():
    tracker = SelectionFreshnessTracker(
        prev_text="word",
        prev_owner_id=1,
        baseline_initialized=True,
    )

    result = tracker.on_click_passive_selection("word", 2)

    assert result == "fresh"
    assert tracker.valid is True


def test_effective_valid_uses_repeat_generation():
    tracker = SelectionFreshnessTracker(valid=True)
    tracker.set_valid(True)
    tracker.mark_repeat_for_current_generation()
    tracker.set_valid(False)

    assert tracker.effective_valid() is True

    tracker.generation += 1

    assert tracker.effective_valid() is False
