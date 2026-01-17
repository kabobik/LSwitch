"""KeyboardController: wrapper around a fake uinput device.

Provides tap_key and replay_events methods to emulate key presses/releases and to
replay recorded events.
"""

class KeyboardController:
    def __init__(self, uinput_device):
        self.uinput = uinput_device

    def tap_key(self, keycode, n_times=1):
        for _ in range(n_times):
            self.uinput.write(1, keycode, 1)  # press
            self.uinput.syn()
            self.uinput.write(1, keycode, 0)  # release
            self.uinput.syn()

    def replay_events(self, events):
        """Replay recorded events through the uinput device.

        Each event is expected to have 'code' and 'value' attributes.
        """
        for ev in events:
            self.uinput.write(1, ev.code, ev.value)
            self.uinput.syn()
