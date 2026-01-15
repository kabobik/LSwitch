import os
import json
import tempfile
import subprocess
import sys
sys.path.insert(0, os.getcwd())
from lswitch_control import LSwitchControlPanel
from PyQt5.QtWidgets import QApplication
import os


def test_save_triggers_auto_apply(monkeypatch, tmp_path):
    # Setup an offscreen QApplication
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])
    from PyQt5.QtGui import QIcon
    panel = LSwitchControlPanel(QIcon())
    # Make sure there's no system config
    monkeypatch.setenv('LSWITCH_TEST_SYSTEM_CONFIG', str(tmp_path / 'etc' / 'lswitch' / 'config.json'))
    # Ensure save will attempt to call pkexec or sudo: monkeypatch subprocess.run
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        class R: pass
        return R()

    monkeypatch.setattr('subprocess.run', fake_run)

    panel.config['apply_system_by_default'] = True
    panel.config['auto_switch'] = True
    ok = panel.save_config()
    assert ok is True
    # Because no system config is present, it will still try to move via pkexec/sudo to default /etc path
    assert any('pkexec' in c or 'sudo' in c for c in calls)
