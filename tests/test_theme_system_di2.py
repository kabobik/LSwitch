import lswitch.utils.theme as theme


class MockSystem:
    def __init__(self):
        self.calls = []
    def run(self, *args, **kwargs):
        self.calls.append(('run', args, kwargs))
        class R: returncode = 1; stdout=''
        return R()


def test_theme_set_system(monkeypatch):
    mock = MockSystem()
    theme.set_system(mock)
    res = theme.get_cinnamon_theme_colors()
    assert any(c[0] == 'run' for c in mock.calls)
    theme.set_system(None)