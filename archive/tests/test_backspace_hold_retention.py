from lswitch.core import LSwitch
import time


def make_lswitch_no_threads(monkeypatch):
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    # Prevent real uinput creation
    class DummyUInput:
        def __init__(self, *a, **k):
            pass
        def write(self, *a, **k):
            pass
        def syn(self):
            pass
    monkeypatch.setattr('evdev.UInput', DummyUInput)
    ls = LSwitch(config_path='config.json')
    return ls


def test_backspace_hold_is_preserved_shortly(monkeypatch):
    ls = make_lswitch_no_threads(monkeypatch)

    ls.backspace_hold_detected = True
    ls.backspace_hold_detected_at = time.time() - 0.2  # recent

    ls.clear_buffer()

    assert ls.backspace_hold_detected is True


def test_backspace_hold_expires_after_window(monkeypatch):
    ls = make_lswitch_no_threads(monkeypatch)

    ls.backspace_hold_detected = True
    ls.backspace_hold_detected_at = time.time() - 1.0  # expired

    ls.clear_buffer()

    assert ls.backspace_hold_detected is False
    assert ls.backspace_hold_detected_at == 0.0
