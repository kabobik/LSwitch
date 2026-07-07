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
