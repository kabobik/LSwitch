from types import SimpleNamespace
import lswitch.core as core_mod


class MockInputHandler:
    def __init__(self):
        self.calls = []

    def handle_event(self, event):
        self.calls.append(event)
        return 'handled'


class MockMonitor:
    def __init__(self):
        self.started = False
        self.thread_layout = 'thread_layout'
        self.thread_file = 'thread_file'
        self.running = False

    def start(self):
        self.started = True
        self.running = True

    def stop(self):
        self.running = False


def make_lswitch_no_threads(**kwargs):
    # Always disable real threads in tests by default
    return core_mod.LSwitch(config_path='config.json', start_threads=False, **kwargs)


def test_input_handler_injection():
    ih = MockInputHandler()
    ls = make_lswitch_no_threads(input_handler=ih)
    ev = SimpleNamespace(type=1, code=2, value=0)
    res = ls.handle_event(ev)
    assert res == 'handled'
    assert ih.calls and ih.calls[0] is ev


def test_layout_monitor_injection_starting():
    mock = MockMonitor()
    ls = core_mod.LSwitch(config_path='config.json', start_threads=True, layout_monitor=mock)
    assert ls.layout_monitor is mock
    assert mock.started is True
    assert ls.layout_thread == 'thread_layout'
    assert ls.layouts_file_monitor_thread == 'thread_file'


def test_layout_monitor_injection_no_start_when_disabled():
    mock = MockMonitor()
    ls = core_mod.LSwitch(config_path='config.json', start_threads=False, layout_monitor=mock)
    # Should accept provided monitor but not start it when start_threads=False
    assert ls.layout_monitor is mock
    assert mock.started is False
    assert ls.layout_thread is None
    assert ls.layouts_file_monitor_thread is None