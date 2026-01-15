import lswitch
from lswitch import LSwitch


def DummyUInput(*args, **kwargs):
    class DU:
        def write(self, *a, **k):
            pass
        def syn(self):
            pass
    return DU()


def test_convert_and_retype_updates_text(monkeypatch):
    # Prevent threads and real uinput
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    monkeypatch.setattr('evdev.UInput', DummyUInput)

    ls = LSwitch(config_path='config.json')
    ls.user_dict = True  # force converted_text path

    original = 'ytdthysq'
    ls.text_buffer = list(original)
    ls.chars_in_buffer = len(original)
    ls.event_buffer = []

    ls.convert_and_retype()

    expected = ls.convert_text(original)
    assert ''.join(ls.text_buffer) == expected
    assert ls.chars_in_buffer == len(original)


def test_convert_and_retype_missing_releases_triggers_fallback(monkeypatch):
    # Prevent threads and real uinput
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    monkeypatch.setattr('evdev.UInput', DummyUInput)

    from types import SimpleNamespace
    from evdev import ecodes

    ls = LSwitch(config_path='config.json')
    ls.user_dict = True

    original = 'test'
    ls.text_buffer = list(original)
    ls.chars_in_buffer = len(original)

    # Simulate events that contain only keydown (no releases)
    events = [SimpleNamespace(code=ecodes.KEY_T, value=1),
              SimpleNamespace(code=ecodes.KEY_E, value=1),
              SimpleNamespace(code=ecodes.KEY_S, value=1),
              SimpleNamespace(code=ecodes.KEY_T, value=1)]
    ls.event_buffer = events

    # Simulate failed replay (no visible typing)
    monkeypatch.setattr(ls.kb, 'replay_events', lambda ev: None)

    calls = []
    def fake_tap(code, n_times=1):
        calls.append((code, n_times))
    monkeypatch.setattr(ls, 'tap_key', fake_tap)

    ls.convert_and_retype()

    expected = ls.convert_text(original)
    assert ''.join(ls.text_buffer) == expected
    # Fallback should have attempted to type (at least one tap per char)
    assert len(calls) >= len(expected)
