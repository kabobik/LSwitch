import os
import sys
import pytest

# Ensure tests can import package when run individually
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import lswitch


def test_monitors_disabled(monkeypatch, tmp_path):
    # Enable test-only mode that disables monitor threads
    monkeypatch.setenv('LSWITCH_TEST_DISABLE_MONITORS', '1')

    # Provide a minimal system config so load_config does not try to read /etc
    sys_cfg_dir = tmp_path / 'etc' / 'lswitch'
    sys_cfg_dir.mkdir(parents=True, exist_ok=True)
    sys_cfg = sys_cfg_dir / 'config.json'
    sys_cfg.write_text('{"debug": true}')
    monkeypatch.setenv('LSWITCH_TEST_SYSTEM_CONFIG', str(sys_cfg))

    # Make sure user config path points to a non-existent file
    monkeypatch.setenv('LSWITCH_TEST_USER_CONFIG', str(tmp_path / 'home' / 'user' / '.config' / 'lswitch' / 'config.json'))

    # Prevent Xlib interactions and heavy platform-specific calls
    monkeypatch.setattr(lswitch, 'XLIB_AVAILABLE', False)
    monkeypatch.setattr(lswitch.LSwitch, 'configure_virtual_keyboard_layouts', lambda self: None)

    ls = lswitch.LSwitch()

    assert getattr(ls, 'layout_thread', None) is None
    assert getattr(ls, 'layouts_file_monitor_thread', None) is None


def test_monitors_enabled(monkeypatch, tmp_path):
    # Ensure variable is not set (normal runtime)
    monkeypatch.delenv('LSWITCH_TEST_DISABLE_MONITORS', raising=False)

    # Minimal system config to satisfy load_config
    sys_cfg_dir = tmp_path / 'etc' / 'lswitch'
    sys_cfg_dir.mkdir(parents=True, exist_ok=True)
    sys_cfg = sys_cfg_dir / 'config.json'
    sys_cfg.write_text('{"debug": true}')
    monkeypatch.setenv('LSWITCH_TEST_SYSTEM_CONFIG', str(sys_cfg))
    monkeypatch.setenv('LSWITCH_TEST_USER_CONFIG', str(tmp_path / 'home' / 'user' / '.config' / 'lswitch' / 'config.json'))

    # Prevent heavyweight platform calls
    monkeypatch.setattr(lswitch, 'XLIB_AVAILABLE', False)
    monkeypatch.setattr(lswitch.LSwitch, 'configure_virtual_keyboard_layouts', lambda self: None)

    # Replace monitor methods with lightweight loops that respect self.running
    import time, threading

    def simple_monitor(self):
        for _ in range(20):
            if not self.running:
                break
            time.sleep(0.01)

    monkeypatch.setattr(lswitch.LSwitch, 'monitor_layout_changes', simple_monitor)
    monkeypatch.setattr(lswitch.LSwitch, 'monitor_layouts_file', simple_monitor)

    ls = lswitch.LSwitch()

    assert isinstance(ls.layout_thread, threading.Thread)
    assert isinstance(ls.layouts_file_monitor_thread, threading.Thread)
    assert ls.layout_thread.is_alive()
    assert ls.layouts_file_monitor_thread.is_alive()

    # Stop threads and join
    ls.running = False
    ls.layout_thread.join(timeout=1)
    ls.layouts_file_monitor_thread.join(timeout=1)

    assert not ls.layout_thread.is_alive()
    assert not ls.layouts_file_monitor_thread.is_alive()
