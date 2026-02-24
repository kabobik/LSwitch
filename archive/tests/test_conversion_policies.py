from lswitch.conversion import ConversionManager


class MockX11:
    def __init__(self, win_class=None):
        self.win_class = win_class

    def get_active_window_class(self):
        return self.win_class


def test_app_policy_via_config():
    cm = ConversionManager(config={'app_policies': {'Code': 'retype'}}, x11_adapter=MockX11(win_class='Code'))
    buf = type('B', (), {'chars_in_buffer': 5})()
    mode = cm.choose_mode(buf, lambda: False, backspace_hold=False)
    assert mode == 'retype'


def test_default_app_policy():
    # When no config provided, DEFAULT_APP_POLICIES should apply
    cm = ConversionManager(config={}, x11_adapter=MockX11(win_class='Code'))
    buf = type('B', (), {'chars_in_buffer': 5})()
    mode = cm.choose_mode(buf, lambda: False, backspace_hold=False)
    assert mode == 'retype'  # from DEFAULT_APP_POLICIES


def test_register_policy_callable():
    cm = ConversionManager(config={}, x11_adapter=None)
    buf = type('B', (), {'chars_in_buffer': 5})()

    def policy(context):
        # prefer selection when buffer contains more than 10 chars
        if context['buffer'].chars_in_buffer > 10:
            return 'selection'
        return None

    cm.register_policy(policy)
    assert cm.choose_mode(type('B', (), {'chars_in_buffer': 5})(), lambda: False, backspace_hold=False) == 'retype'
    assert cm.choose_mode(type('B', (), {'chars_in_buffer': 20})(), lambda: False, backspace_hold=False) == 'selection'
