import os
import sys
import shutil
import pytest
try:
    from PyQt5.QtWidgets import QApplication
    sys.path.insert(0, os.getcwd())
    from lswitch_control import LSwitchControlPanel
except Exception:
    pytest.skip("GUI tray removed; skipping GUI tests", allow_module_level=True)


def test_gui_autostart_toggle(monkeypatch, tmp_path):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])

    # Use a temp HOME so we don't touch real autostart
    monkeypatch.setenv('HOME', str(tmp_path / 'home' / 'user'))

    # Ensure no autostart file initially
    panel = LSwitchControlPanel(None)

    autostart_path = os.path.expanduser('~/.config/autostart/lswitch-control.desktop')
    if os.path.exists(autostart_path):
        os.remove(autostart_path)

    # Ensure system-level autostart is not present for this test
    monkeypatch.setattr(panel, '_system_autostart_present', lambda: False)

    # Simulate clicking to enable
    panel.gui_autostart_action.setChecked(True)
    panel.toggle_gui_autostart()
    assert os.path.exists(autostart_path)
    assert panel.gui_autostart_action.isChecked()

    # Now toggle off (no system-level autostart present)
    panel.gui_autostart_action.setChecked(False)
    panel.toggle_gui_autostart()
    assert not os.path.exists(autostart_path)
    assert not panel.gui_autostart_action.isChecked()

    # Create a local autostart file and simulate a system-managed autostart — disabling should be blocked
    os.makedirs(os.path.dirname(autostart_path), exist_ok=True)
    with open(autostart_path, 'w') as f:
        f.write('[Desktop Entry]\n')
    monkeypatch.setattr(panel, '_system_autostart_present', lambda: True)

    # Try to disable — should remain enabled and local file preserved
    panel.gui_autostart_action.setChecked(False)
    panel.toggle_gui_autostart()
    assert os.path.exists(autostart_path)
    assert panel.gui_autostart_action.isChecked()

    app.quit()
