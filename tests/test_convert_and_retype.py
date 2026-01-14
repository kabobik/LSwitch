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
