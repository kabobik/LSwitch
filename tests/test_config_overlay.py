import os
import json
import tempfile
import shutil
import sys
# Ensure project root is on sys.path for imports
sys.path.insert(0, os.getcwd())
from lswitch import LSwitch


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def test_overlay(tmp_path, monkeypatch):
    # Prepare fake system and user configs
    sys_cfg = tmp_path / "etc" / "lswitch"
    sys_cfg.mkdir(parents=True)
    sys_path = str(sys_cfg / 'config.json')
    write_json(sys_path, {"auto_switch": False, "allow_user_overrides": True})

    user_cfg_dir = tmp_path / "home" / "user" / ".config" / "lswitch"
    user_cfg_dir.mkdir(parents=True)
    user_path = str(user_cfg_dir / 'config.json')
    write_json(user_path, {"auto_switch": True})

    # Monkeypatch paths
    monkeypatch.setenv('HOME', str(tmp_path / 'home' / 'user'))
    # Ensure /etc path is found
    monkeypatch.setenv('LSWITCH_TEST_SYSTEM_CONFIG', sys_path)

    # Create a bare LSwitch instance without __init__ to avoid side effects
    ls = LSwitch.__new__(LSwitch)
    ls.config = {}
    cfg = LSwitch.load_config(ls)  # instance method call
    assert cfg['auto_switch'] is True


def test_disable_overrides(tmp_path, monkeypatch):
    sys_cfg = tmp_path / "etc" / "lswitch"
    sys_cfg.mkdir(parents=True)
    sys_path = str(sys_cfg / 'config.json')
    write_json(sys_path, {"auto_switch": False, "allow_user_overrides": False})

    user_cfg_dir = tmp_path / "home" / "user" / ".config" / "lswitch"
    user_cfg_dir.mkdir(parents=True)
    user_path = str(user_cfg_dir / 'config.json')
    write_json(user_path, {"auto_switch": True})

    monkeypatch.setenv('HOME', str(tmp_path / 'home' / 'user'))
    monkeypatch.setenv('LSWITCH_TEST_SYSTEM_CONFIG', sys_path)

    ls = LSwitch.__new__(LSwitch)
    ls.config = {}
    cfg = LSwitch.load_config(ls)
    assert cfg['auto_switch'] is False
