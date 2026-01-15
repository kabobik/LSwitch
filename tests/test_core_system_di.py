from types import SimpleNamespace
import lswitch.core as core_mod


class MockSystem:
    def __init__(self):
        self.calls = []

    def xinput_list_id(self, name, timeout=2):
        self.calls.append(('xinput', name, timeout))
        return SimpleNamespace(stdout='123')

    def run(self, *args, **kwargs):
        self.calls.append(('run', args, kwargs))
        return SimpleNamespace(stdout='')

    def xclip_get(self, selection='primary', timeout=0.3):
        self.calls.append(('xclip_get', selection, timeout))
        return SimpleNamespace(stdout='clipboard')

    def xdotool_key(self, sequence, timeout=0.3, **kwargs):
        self.calls.append(('xdotool', sequence, timeout))
        return SimpleNamespace(stdout='')


def make_lswitch_no_threads(system=None):
    return core_mod.LSwitch(config_path='config.json', start_threads=False, system=system)


def test_configure_virtual_keyboard_uses_injected_system():
    mock = MockSystem()
    ls = make_lswitch_no_threads(system=mock)
    ls.layouts = ['en', 'ru']
    ls.configure_virtual_keyboard_layouts()

    assert any(c[0] == 'xinput' for c in mock.calls)
    assert any(c[0] == 'run' and 'setxkbmap' in c[1][0] for c in mock.calls)


def test_has_selection_and_update_snapshot_uses_injected_system():
    mock = MockSystem()
    ls = make_lswitch_no_threads(system=mock)
    ls.last_known_selection = 'old'
    assert ls.has_selection() is True
    ls.update_selection_snapshot()
    assert ls.last_known_selection == 'clipboard'