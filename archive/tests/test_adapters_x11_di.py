import lswitch.adapters.x11 as x11


class MockSystem:
    def __init__(self):
        self.record = []
    def xclip_get(self, selection='primary', timeout=0.3):
        self.record.append(('xclip_get', selection, timeout))
        class R: stdout = 'MOCK'
        return R()
    def xclip_set(self, text, selection='clipboard', timeout=0.5):
        self.record.append(('xclip_set', text, selection, timeout))
    def xdotool_key(self, seq, timeout=0.3, **kwargs):
        self.record.append(('xdotool', seq))
    def run(self, *args, **kwargs):
        self.record.append(('run', args))
        class R: stdout = 'WIN'
        return R()


def test_adapter_set_system_and_use(monkeypatch):
    mock = MockSystem()
    x11.set_system(mock)

    assert x11.get_primary_selection() == 'MOCK'
    assert x11.get_clipboard() == 'MOCK'
    x11.set_clipboard('x')
    x11.paste_clipboard()
    x11.cut_selection()

    assert ('xclip_get', 'primary', 0.3) in mock.record
    assert ('xclip_get', 'clipboard', 0.3) in mock.record
    assert any(r[0] == 'xclip_set' for r in mock.record)
    assert any(r[0] == 'xdotool' for r in mock.record)

    # cleanup
    x11.set_system(None)