"""Input event routing facade."""

from __future__ import annotations

from collections.abc import Callable

from lswitch.core.events import Event


class InputEventRouter:
    """Routes input events to the current input handlers.

    The first migration step keeps behavior in the existing handlers while
    moving EventBus wiring to a dedicated object. Later steps can move routing
    branches here without changing the public app facade.
    """

    def __init__(
        self,
        *,
        on_key_press: Callable[[Event], None],
        on_key_release: Callable[[Event], None],
        on_key_repeat: Callable[[Event], None],
        on_mouse_click: Callable[[Event], None],
        on_mouse_release: Callable[[Event], None],
    ):
        self._on_key_press = on_key_press
        self._on_key_release = on_key_release
        self._on_key_repeat = on_key_repeat
        self._on_mouse_click = on_mouse_click
        self._on_mouse_release = on_mouse_release

    def on_key_press(self, event: Event) -> None:
        self._on_key_press(event)

    def on_key_release(self, event: Event) -> None:
        self._on_key_release(event)

    def on_key_repeat(self, event: Event) -> None:
        self._on_key_repeat(event)

    def on_mouse_click(self, event: Event) -> None:
        self._on_mouse_click(event)

    def on_mouse_release(self, event: Event) -> None:
        self._on_mouse_release(event)
