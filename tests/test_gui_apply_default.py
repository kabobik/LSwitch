import os
import json
import tempfile
import subprocess
import sys
import pytest
sys.path.insert(0, os.getcwd())
try:
    from lswitch_control import LSwitchControlPanel
    from PyQt5.QtWidgets import QApplication
except Exception:
    pytest.skip("GUI tray removed; skipping GUI tests", allow_module_level=True)
import os


def test_save_triggers_auto_apply(monkeypatch, tmp_path):
    # Setup an offscreen QApplication
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])
    from PyQt5.QtGui import QIcon
    panel = LSwitchControlPanel(QIcon())
    # Make sure there's no system config
    monkeypatch.setenv('LSWITCH_TEST_SYSTEM_CONFIG', str(tmp_path / 'etc' / 'lswitch' / 'config.json'))
    # Save should write local user config and not attempt system apply
    panel.config['auto_switch'] = True
    ok = panel.save_config()
    assert ok is True
    # verify user config written
    cfg_path = os.path.expanduser('~/.config/lswitch/config.json')
    assert os.path.exists(cfg_path)

