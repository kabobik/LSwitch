import os
import json
import tempfile
import shutil
import sys
# Ensure project root is on sys.path for imports
sys.path.insert(0, os.getcwd())
from lswitch.core import LSwitch


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def test_user_config_applies(tmp_path, monkeypatch):
    user_cfg_dir = tmp_path / "home" / "user" / ".config" / "lswitch"
    user_cfg_dir.mkdir(parents=True)
    user_path = str(user_cfg_dir / 'config.json')
    write_json(user_path, {"auto_switch": True})

    # Monkeypatch HOME so load_config picks user path
    monkeypatch.setenv('HOME', str(tmp_path / 'home' / 'user'))

    ls = LSwitch.__new__(LSwitch)
    ls.config = {}
    cfg = LSwitch.load_config(ls)
    assert cfg['auto_switch'] is True


def test_user_config_created_if_missing(tmp_path, monkeypatch):
    # No user config present — load_config should create a default user config
    monkeypatch.setenv('HOME', str(tmp_path / 'home' / 'user'))

    ls = LSwitch.__new__(LSwitch)
    ls.config = {}
    cfg = LSwitch.load_config(ls)
    # Should have default fields
    assert 'auto_switch' in cfg
    # The file should be created on disk
    created_path = tmp_path / 'home' / 'user' / '.config' / 'lswitch' / 'config.json'
    assert created_path.exists()

