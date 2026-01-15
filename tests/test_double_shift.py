import time

from lswitch import core


def test_double_shift_triggers_conversion_manager(tmp_path, monkeypatch):
    # Monkeypatch display to avoid connecting to a real X server
    class DummyDisplay:
        def __init__(self):
            pass
    monkeypatch.setattr(core, 'display', type('m', (object,), {'Display': lambda *a, **k: DummyDisplay()}))

    # Monkeypatch evdev.UInput to avoid creating a real uinput device
    class DummyUInput:
        def __init__(self, *a, **k):
            pass
        def close(self):
            pass
        def write(self, *a, **k):
            pass
        def syn(self):
            pass

    monkeypatch.setattr(core, 'evdev', type('m', (object,), {'UInput': DummyUInput}))

    # Ensure user config does not interfere with test
    monkeypatch.setenv('HOME', str(tmp_path))

    # Create an empty config file so load_config has a valid path
    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text("{}", encoding='utf-8')
    ls = core.LSwitch(config_path=str(cfg_file), start_threads=False)

    # Attach a dummy conversion manager and stub has_selection
    class DummyCM:
        def __init__(self):
            self.called = False

        def choose_mode(self, buffer, has_sel_fn, backspace_hold=False):
            self.called = True
            return 'retype'

    cm = DummyCM()
    ls.conversion_manager = cm
    ls.has_selection = lambda: False

    # Create a synthetic shift release event
    ev = type('E', (), {})()
    ev.type = core.ecodes.EV_KEY
    ev.code = core.ecodes.KEY_LEFTSHIFT
    ev.value = 0

    # Simulate that previous shift press was recently (within timeout)
    ls.last_shift_press = time.time() - (ls.double_click_timeout / 2)

    # Call the exposed helper that encapsulates the double-shift behavior
    ls.on_double_shift()

    assert cm.called is True
