import time

from lswitch import core


def test_double_shift_calls_convert_and_retype_when_buffer_has_chars(monkeypatch, tmp_path):
    # Prepare
    monkeypatch.setenv('HOME', str(tmp_path))
    class DummyUInput:
        def __init__(self, *a, **k):
            pass
        def close(self):
            pass
    monkeypatch.setattr(core, 'evdev', type('m', (), {'UInput': DummyUInput}))

    ls = core.LSwitch(config_path=str(tmp_path / "cfg.json"), start_threads=False)
    (tmp_path / "cfg.json").write_text("{}", encoding='utf-8')

    called = {'retype': False}
    def fake_retype():
        called['retype'] = True
    ls.convert_and_retype = fake_retype

    # Simulate buffer with characters
    ls.chars_in_buffer = 3
    ls.text_buffer = list('abc')
    # Ensure selection check returns False so we hit retype path
    ls.has_selection = lambda: False

    ls.on_double_shift()

    assert called['retype'] is True


def test_double_shift_calls_convert_selection_when_buffer_empty(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    class DummyUInput:
        def __init__(self, *a, **k):
            pass
        def close(self):
            pass
    monkeypatch.setattr(core, 'evdev', type('m', (), {'UInput': DummyUInput}))

    ls = core.LSwitch(config_path=str(tmp_path / "cfg.json"), start_threads=False)
    (tmp_path / "cfg.json").write_text("{}", encoding='utf-8')

    called = {'sel': False}
    def fake_sel():
        called['sel'] = True
    ls.convert_selection = fake_sel

    # Simulate empty buffer
    ls.chars_in_buffer = 0

    # Stub has_selection to True so selection path is taken
    ls.has_selection = lambda: True

    ls.on_double_shift()

    assert called['sel'] is True
