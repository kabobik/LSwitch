"""Tests for typed key-event buffer helpers."""

from __future__ import annotations

from lswitch.core.events import KeyEventData
from lswitch.core.states import StateContext
from lswitch.core.typed_buffer import TypedBufferService


KEY_G = 34
KEY_H = 35
KEY_B = 48
KEY_SPACE = 57


def _key(code: int) -> KeyEventData:
    return KeyEventData(code=code, value=1, device_name="test")


def test_append_event_sets_shift_and_count():
    context = StateContext()
    service = TypedBufferService()
    event = _key(KEY_G)

    service.append_event(context, event, shifted=True)

    assert context.chars_in_buffer == 1
    assert context.event_buffer == [event]
    assert event.shifted is True
    assert service.decode(context.event_buffer) == "G"


def test_pop_event_preserves_count_for_key_press_backspace_semantics():
    context = StateContext()
    service = TypedBufferService()
    service.append_event(context, _key(KEY_G), shifted=False)

    popped = service.pop_event(context)

    assert popped.code == KEY_G
    assert context.event_buffer == []
    assert context.chars_in_buffer == 1


def test_decrement_count_clamps_at_zero():
    context = StateContext()
    service = TypedBufferService()

    service.decrement_count(context)

    assert context.chars_in_buffer == 0


def test_last_word_skips_trailing_spaces():
    context = StateContext()
    service = TypedBufferService()
    for code in [KEY_G, KEY_H, KEY_B, KEY_SPACE]:
        service.append_event(context, _key(code), shifted=False)

    token = service.last_word(context)

    assert token.text == "ghb"
    assert [event.code for event in token.events] == [KEY_G, KEY_H, KEY_B]
    assert token.has_trailing_space is True


def test_last_word_returns_text_after_last_space():
    context = StateContext()
    service = TypedBufferService()
    for code in [KEY_G, KEY_SPACE, KEY_H, KEY_B]:
        service.append_event(context, _key(code), shifted=False)

    token = service.last_word(context)

    assert token.text == "hb"
    assert [event.code for event in token.events] == [KEY_H, KEY_B]


def test_prepare_retype_buffer_restores_sticky_when_context_empty():
    context = StateContext()
    service = TypedBufferService()
    sticky = [_key(KEY_G), _key(KEY_H)]

    result = service.prepare_retype_buffer(
        context,
        sticky_events=sticky,
        selection_valid=False,
    )

    assert result.restored_from_sticky is True
    assert result.events == sticky
    assert result.count == 2
    assert context.event_buffer == sticky
    assert context.chars_in_buffer == 2


def test_prepare_retype_buffer_trims_to_last_word_and_keeps_trailing_space():
    context = StateContext()
    service = TypedBufferService()
    for code in [KEY_G, KEY_SPACE, KEY_H, KEY_B, KEY_SPACE]:
        service.append_event(context, _key(code), shifted=False)

    result = service.prepare_retype_buffer(
        context,
        sticky_events=[],
        selection_valid=False,
    )

    assert result.trimmed_to_last_word is True
    assert result.original_count == 5
    assert result.count == 3
    assert result.trailing_space_count == 1
    assert [event.code for event in result.events] == [KEY_H, KEY_B, KEY_SPACE]
    assert context.chars_in_buffer == 3


def test_prepare_retype_buffer_does_not_trim_selection_mode():
    context = StateContext()
    service = TypedBufferService()
    for code in [KEY_G, KEY_SPACE, KEY_H]:
        service.append_event(context, _key(code), shifted=False)

    result = service.prepare_retype_buffer(
        context,
        sticky_events=[],
        selection_valid=True,
    )

    assert result.trimmed_to_last_word is False
    assert result.count == 3
    assert [event.code for event in result.events] == [KEY_G, KEY_SPACE, KEY_H]
