"""Layout monitoring utilities.

Provides LayoutMonitor to watch for layout changes (polling fallback)
and to monitor a runtime layout file published by control panel.
"""
from __future__ import annotations

import os
import json
import time
import threading
from typing import Optional


class LayoutMonitor:
    """Monitor layout changes and runtime layout file.

    Parameters
    - lswitch: object with attributes: config(dict), layout_lock(threading.Lock),
      current_layout (string), layouts (list) and methods get_current_layout().
    - poll_interval: seconds between polls (used in tests to speed up)
    - runtime_dir: optional override for XDG_RUNTIME_DIR (tests)
    """
    def __init__(self, lswitch, poll_interval: float = 1.0, runtime_dir: Optional[str] = None):
        self.lswitch = lswitch
        self.poll_interval = poll_interval
        self.running = False
        self.thread_layout = None
        self.thread_file = None
        self.runtime_dir = runtime_dir or os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
        self.layouts_file = os.path.join(self.runtime_dir, 'lswitch_layouts.json')

    def start(self):
        if self.running:
            return
        self.running = True
        # Prefer explicit hooks on the LSwitch instance when available so
        # tests can monkeypatch `LSwitch.monitor_layout_changes` /
        # `LSwitch.monitor_layouts_file` and have them run in the monitor threads.
        layout_target = getattr(self.lswitch, 'monitor_layout_changes', self._monitor_layout_changes)
        file_target = getattr(self.lswitch, 'monitor_layouts_file', self._monitor_layouts_file)
        self.thread_layout = threading.Thread(target=layout_target, daemon=True)
        self.thread_file = threading.Thread(target=file_target, daemon=True)
        self.thread_layout.start()
        self.thread_file.start()

    def stop(self, timeout: float = 1.0):
        self.running = False
        if self.thread_layout:
            self.thread_layout.join(timeout=timeout)
        if self.thread_file:
            self.thread_file.join(timeout=timeout)

    def _monitor_layout_changes(self):
        last_layout = None
        try:
            last_layout = self.lswitch.get_current_layout()
        except Exception:
            last_layout = getattr(self.lswitch, 'current_layout', None)

        while self.running:
            try:
                new_layout = self.lswitch.get_current_layout()
                with getattr(self.lswitch, 'layout_lock', threading.Lock()):
                    if new_layout != last_layout:
                        old = last_layout
                        last_layout = new_layout
                        self.lswitch.current_layout = new_layout
                        if self.lswitch.config.get('debug'):
                            print(f"🔄 Layout changed: {old} → {new_layout}")
                time.sleep(self.poll_interval)
            except Exception as e:
                if self.lswitch.config.get('debug'):
                    print(f"⚠️ LayoutMonitor error: {e}")
                time.sleep(1)

    def _monitor_layouts_file(self):
        last_mtime = 0
        while self.running:
            try:
                if os.path.exists(self.layouts_file):
                    current_mtime = os.path.getmtime(self.layouts_file)
                    if current_mtime != last_mtime:
                        last_mtime = current_mtime
                        try:
                            with open(self.layouts_file, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                new_layouts = data.get('layouts', [])
                                if new_layouts and new_layouts != self.lswitch.layouts:
                                    old = self.lswitch.layouts
                                    self.lswitch.layouts = new_layouts
                                    if self.lswitch.config.get('debug'):
                                        print(f"🔄 Layouts updated from file: {old} → {new_layouts}")
                        except Exception as e:
                            if self.lswitch.config.get('debug'):
                                print(f"⚠️ Error reading layouts file: {e}")
                # Use poll_interval (test-friendly). In production, choose a sensible default when constructing monitor.
                time.sleep(self.poll_interval)
            except Exception as e:
                if self.lswitch.config.get('debug'):
                    print(f"⚠️ Layout file monitor error: {e}")
                time.sleep(5)
