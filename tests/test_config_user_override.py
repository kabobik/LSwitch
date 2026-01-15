import json
import os
import tempfile

from lswitch.core import LSwitch, validate_config


def test_user_config_overrides_system(tmp_path, monkeypatch):
    # Create a system config and a user config with differing values
    sys_cfg = tmp_path / "system_config.json"
    sys_cfg.write_text(json.dumps({'double_click_timeout': 0.5, 'auto_switch': False}), encoding='utf-8')

    user_cfg_dir = tmp_path / "user_config_dir"
    user_cfg_dir.mkdir()
    user_cfg = user_cfg_dir / "config.json"
    user_cfg.write_text(json.dumps({'auto_switch': True, 'debug': True}), encoding='utf-8')

    # Point HOME to our tmp dir so that ~/.config/lswitch/config.json is used
    monkeypatch.setenv('HOME', str(user_cfg_dir.parent))
    # ensure the exact path matches ~/.config/lswitch/config.json
    user_conf_path = os.path.join(str(user_cfg_dir.parent), '.config', 'lswitch')
    os.makedirs(user_conf_path, exist_ok=True)
    os.replace(str(user_cfg), os.path.join(user_conf_path, 'config.json'))

    ls = LSwitch(config_path=str(sys_cfg), start_threads=False)

    # System had auto_switch False, user config sets it True — user overrides
    assert ls.config['auto_switch'] is True
    assert ls.config['debug'] is True
    assert ls.config['_config_path'] == str(sys_cfg)
    assert ls.config['_user_config_path'] is not None
