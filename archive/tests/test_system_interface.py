import types
import lswitch.system as system_mod
from types import SimpleNamespace


class DummyProc:
    def __init__(self, stdout='ok'):
        self.stdout = stdout


class MockSystem:
    def __init__(self):
        self.calls = []

    def run(self, *args, **kwargs):
        self.calls.append(('run', args, kwargs))
        return DummyProc(stdout='run')

    def Popen(self, *args, **kwargs):
        self.calls.append(('popen', args, kwargs))
        return None

    def xdotool_key(self, sequence, timeout=0.3, **kwargs):
        self.calls.append(('xdotool', sequence, timeout, kwargs))
        return DummyProc(stdout='xdotool')

    def setxkbmap_query(self, timeout=2):
        self.calls.append(('setxkb', timeout))
        return DummyProc(stdout='setxkb')

    def xinput_list_id(self, name, timeout=2):
        self.calls.append(('xinput', name, timeout))
        return DummyProc(stdout='42')

    def xclip_get(self, selection='primary', timeout=0.5):
        self.calls.append(('xclip_get', selection, timeout))
        return DummyProc(stdout='clipboard')

    def xclip_set(self, text, selection='clipboard', timeout=0.5):
        self.calls.append(('xclip_set', text, selection, timeout))
        return DummyProc(stdout='')


def test_replace_system_instance_and_call_wrappers(monkeypatch):
    mock = MockSystem()
    monkeypatch.setattr(system_mod, 'SYSTEM', mock)

    # Top-level convenience functions should dispatch to the instance
    assert system_mod.run(['echo']) .stdout == 'run'
    assert system_mod.xdotool_key('ctrl+v').stdout == 'xdotool'
    assert system_mod.setxkbmap_query().stdout == 'setxkb'
    assert system_mod.xinput_list_id('foo').stdout == '42'
    assert system_mod.xclip_get('primary').stdout == 'clipboard'
    system_mod.xclip_set('hey', selection='clipboard')

    # Ensure adapter code (adapters/x11) uses system module and therefore the mock
    import lswitch.adapters.x11 as x11
    res = x11.get_primary_selection(timeout=0.1)
    assert res == 'clipboard'
    # mock recorded runs
    assert any(c[0] == 'xclip_get' for c in mock.calls)
