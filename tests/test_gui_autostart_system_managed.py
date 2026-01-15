import os
import sys
import pytest
try:
    from PyQt5.QtWidgets import QApplication
    sys.path.insert(0, os.getcwd())
    from lswitch_control import LSwitchControlPanel
except Exception:
    pytest.skip("GUI tray removed; skipping GUI tests", allow_module_level=True)


def test_gui_autostart_system_managed(monkeypatch, tmp_path):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])

    # Use temp HOME so we don't touch real autostart
    monkeypatch.setenv('HOME', str(tmp_path / 'home' / 'user'))

    panel = LSwitchControlPanel(None)

    autostart_path = os.path.expanduser('~/.config/autostart/lswitch-control.desktop')
    # Ensure no local autostart file exists
    if os.path.exists(autostart_path):
        os.remove(autostart_path)

    # Simulate that system-level autostart is present and provide a fake system path
    fake_sys = '/etc/xdg/autostart/lswitch-control.desktop'
    monkeypatch.setattr(panel, '_system_autostart_present', lambda: fake_sys)

    # Capture messages
    messages = []
    monkeypatch.setattr(panel, 'showMessage', lambda title, text, icon, timeout: messages.append((title, text, timeout)))

    # Try to disable (user clicks checkbox to uncheck)
    panel.gui_autostart_action.setChecked(False)
    panel.toggle_gui_autostart()

    # Since system-level autostart is present, GUI should remain checked and no local file should be created
    assert panel.gui_autostart_action.isChecked()
    assert not os.path.exists(autostart_path)
    assert messages, "showMessage should have been called"
    assert fake_sys in messages[-1][1]

    app.quit()
