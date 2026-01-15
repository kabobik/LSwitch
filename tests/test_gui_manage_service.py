import os
from PyQt5.QtWidgets import QApplication
from lswitch_control import LSwitchControlPanel, set_system


def test_gui_service_control_disabled(monkeypatch, tmp_path):
    # Ensure config is local to tmp dir
    monkeypatch.setenv('HOME', str(tmp_path / 'home' / 'user'))
    os.makedirs(str(tmp_path / 'home' / 'user') + '/.config/lswitch', exist_ok=True)

    # Start offscreen app
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])

    panel = LSwitchControlPanel(None)

    # Prepare a mock system that would record runs
    calls = []
    class MockSys:
        def run(self, *args, **kwargs):
            calls.append((args, kwargs))
            class R:
                stdout = 'active'
            return R()
    mock = MockSys()
    set_system(mock)

    # Disable GUI management in config
    panel.config['gui_manage_service'] = False
    panel.save_config()

    msgs = []
    monkeypatch.setattr(panel, 'showMessage', lambda *a, **k: msgs.append((a, k)))

    # Clear earlier calls (status checks) and attempt to start service
    calls.clear()

    panel.start_service()

    # The panel may call 'is-active' status checks; ensure it did not issue a 'start' command
    assert all('start' not in (a[0] if isinstance(a, (list, tuple)) else a for a in call[0][0]) for call in calls), 'system.run should not call start when gui_manage_service is False'
    assert msgs, 'User should see a message when management is disabled'

    app.quit()
