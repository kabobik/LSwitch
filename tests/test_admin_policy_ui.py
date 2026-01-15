import os
import sys
sys.path.insert(0, os.getcwd())
from lswitch_control import LSwitchControlPanel
from PyQt5.QtWidgets import QApplication


def test_admin_policy_disables_actions(monkeypatch, tmp_path):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])
    # write a system config that disables overrides
    syscfg = tmp_path / 'etc' / 'lswitch'
    syscfg.mkdir(parents=True)
    scp = syscfg / 'config.json'
    scp.write_text('{"allow_user_overrides": false}')
    monkeypatch.setenv('LSWITCH_TEST_SYSTEM_CONFIG', str(scp))

    panel = LSwitchControlPanel(None)

    # The actions should be disabled
    assert not panel.auto_switch_action.isEnabled()
    assert not panel.user_dict_action.isEnabled()
    assert not panel.apply_global_default_action.isEnabled()
    # Apply now should still be enabled
    assert panel.apply_global_now_action.isEnabled()
