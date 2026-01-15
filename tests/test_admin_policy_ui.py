import os
import sys
import pytest
sys.path.insert(0, os.getcwd())
try:
    from lswitch_control import LSwitchControlPanel
    from PyQt5.QtWidgets import QApplication
except Exception:
    pytest.skip("GUI tray removed; skipping GUI tests", allow_module_level=True)


def test_user_options_present_and_enabled(monkeypatch, tmp_path):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])

    panel = LSwitchControlPanel(None)

    # User options should be present and enabled (no admin policy exists)
    assert panel.auto_switch_action.isEnabled()
    assert panel.user_dict_action.isEnabled()
    # Global-apply actions should not exist
    assert not hasattr(panel, 'apply_global_default_action')
    assert not hasattr(panel, 'apply_global_now_action')
