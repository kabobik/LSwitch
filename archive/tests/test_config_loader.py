import os
import json
import textwrap

import pytest

import importlib.util
import os
spec = importlib.util.spec_from_file_location('lswitch_config', os.path.join(os.path.dirname(__file__), '..', 'lswitch', 'config.py'))
cfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)


def test_load_config_uses_user_config(tmp_path, monkeypatch):
    """Test that load_config uses user config from ~/.config/lswitch/"""
    # user config
    home = tmp_path / 'home' / 'user'
    user_cfg_dir = home / '.config' / 'lswitch'
    user_cfg_dir.mkdir(parents=True)
    u = user_cfg_dir / 'config.json'
    u.write_text(json.dumps({'auto_switch': True, 'auto_switch_threshold': 8}), encoding='utf-8')

    monkeypatch.setenv('HOME', str(home))

    # Load with no explicit path — should use user config
    out = cfg.load_config(None, debug=True)
    assert out['auto_switch'] is True
    assert out['auto_switch_threshold'] == 8
    assert out['_config_path'] == str(u)


def test_sanitize_and_trailing_commas(tmp_path):
    bad_cfg = tmp_path / 'cfg.json'
    bad_cfg.write_text(textwrap.dedent('''
        {
            # comment here
            "double_click_timeout": 0.5,
            "debug": true,
        }
    '''), encoding='utf-8')

    out = cfg.load_config(str(bad_cfg), debug=True)
    assert out['double_click_timeout'] == 0.5
    assert out['debug'] is True


def test_validate_config_rejects_bad_values():
    with pytest.raises(ValueError):
        cfg.validate_config({'double_click_timeout': 'bad'})
    with pytest.raises(ValueError):
        cfg.validate_config({'debug': 'yes'})
    with pytest.raises(ValueError):
        cfg.validate_config({'user_dict_min_weight': -1})
    with pytest.raises(ValueError):
        cfg.validate_config({'auto_switch_threshold': -1})
