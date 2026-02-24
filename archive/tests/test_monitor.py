import os
import json
import time
import threading

import importlib.util

# Import LayoutMonitor directly from file to avoid package shadowing
spec = importlib.util.spec_from_file_location('lsmonitor', os.path.join(os.path.dirname(__file__), '..', 'lswitch', 'monitor.py'))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
LayoutMonitor = monitor.LayoutMonitor


class DummyLS:
    def __init__(self):
        self.config = {'debug': False}
        self.layout_lock = threading.Lock()
        self.current_layout = 'en'
        self.layouts = ['en', 'ru']
        self._cnt = 0

    def get_current_layout(self):
        self._cnt += 1
        # switch to 'ru' after a few calls
        return 'ru' if self._cnt > 2 else 'en'


def test_layout_monitor_polls_changes():
    ls = DummyLS()
    lm = LayoutMonitor(ls, poll_interval=0.01)
    lm.start()
    try:
        time.sleep(0.1)
        assert ls.current_layout == 'ru'
    finally:
        lm.stop()


def test_layouts_file_monitor_updates_layouts(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    layouts_file = runtime / 'lswitch_layouts.json'

    ls = DummyLS()
    lm = LayoutMonitor(ls, poll_interval=0.01, runtime_dir=str(runtime))

    lm.start()
    try:
        # write file
        layouts_file.write_text(json.dumps({'layouts': ['en', 'fr']}), encoding='utf-8')
        time.sleep(0.2)
        assert ls.layouts == ['en', 'fr']
    finally:
        lm.stop()
