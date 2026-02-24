"""KeyboardController: wrapper around a fake uinput device.

Provides tap_key and replay_events methods to emulate key presses/releases and to
replay recorded events.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evdev import UInput


class KeyboardController:
    def __init__(self, uinput_device: UInput) -> None:
        self.uinput = uinput_device

    def tap_key(self, keycode: int, n_times: int = 1) -> None:
        for _ in range(n_times):
            self.uinput.write(1, keycode, 1)  # press
            self.uinput.syn()
            self.uinput.write(1, keycode, 0)  # release
            self.uinput.syn()

    def replay_events(self, events: list) -> None:
        """Replay recorded events through the uinput device.

        Each event is expected to have 'code' and 'value' attributes.
        """
        for ev in events:
            self.uinput.write(1, ev.code, ev.value)
            self.uinput.syn()
