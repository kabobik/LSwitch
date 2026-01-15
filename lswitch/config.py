"""Configuration loader and validator for LSwitch.

Provides `load_config(path)` which reads a JSON config (with comment
and trailing-comma tolerant sanitizer) and merges user config override
from `~/.config/lswitch/config.json`.

Also provides `validate_config(conf)` which normalizes and validates
config keys and raises ValueError on invalid values.
"""
from __future__ import annotations

import os
import json


def _sanitize_json_text(s: str) -> str:
    import re
    s = re.sub(r"^[ \t]*#.*$", "", s, flags=re.MULTILINE)
    s = re.sub(r"//.*$", "", s, flags=re.MULTILINE)
    s = re.sub(r",[ \t\r\n]+(\}|\])", r"\1", s)
    return s


def validate_config(conf: dict) -> dict:
    """Validate and normalize configuration dictionary.

    Returns a normalized dict; raises ValueError on invalid keys.
    """
    if conf is None:
        conf = {}

    defaults = {
        'double_click_timeout': 0.3,
        'debug': False,
        'switch_layout_after_convert': True,
        'layout_switch_key': 'Alt_L+Shift_L',
        'auto_switch': False,
        'user_dict_enabled': False,
        'user_dict_min_weight': 2,
    }

    out = dict(defaults)

    # double_click_timeout: positive number between 0.05 and 10
    dct = conf.get('double_click_timeout', defaults['double_click_timeout'])
    try:
        dct_val = float(dct)
        if not (0.05 <= dct_val <= 10.0):
            raise ValueError('double_click_timeout must be between 0.05 and 10.0')
        out['double_click_timeout'] = dct_val
    except Exception:
        raise ValueError(f"Invalid 'double_click_timeout': {dct}")

    # debug
    dbg = conf.get('debug', defaults['debug'])
    if not isinstance(dbg, bool):
        raise ValueError("Invalid 'debug' flag: must be boolean")
    out['debug'] = dbg

    # switch_layout_after_convert
    sl = conf.get('switch_layout_after_convert', defaults['switch_layout_after_convert'])
    if not isinstance(sl, bool):
        raise ValueError("Invalid 'switch_layout_after_convert': must be boolean")
    out['switch_layout_after_convert'] = sl

    # layout_switch_key
    lsk = conf.get('layout_switch_key', defaults['layout_switch_key'])
    if not isinstance(lsk, str) or not lsk:
        raise ValueError("Invalid 'layout_switch_key': must be a non-empty string")
    out['layout_switch_key'] = lsk

    # auto_switch
    autos = conf.get('auto_switch', defaults['auto_switch'])
    if not isinstance(autos, bool):
        raise ValueError("Invalid 'auto_switch': must be boolean")
    out['auto_switch'] = autos

    # user_dict_enabled
    ude = conf.get('user_dict_enabled', defaults['user_dict_enabled'])
    if not isinstance(ude, bool):
        raise ValueError("Invalid 'user_dict_enabled': must be boolean")
    out['user_dict_enabled'] = ude

    # user_dict_min_weight
    udw = conf.get('user_dict_min_weight', defaults['user_dict_min_weight'])
    try:
        udw_i = int(udw)
        if udw_i < 0:
            raise ValueError('user_dict_min_weight must be >= 0')
        out['user_dict_min_weight'] = udw_i
    except Exception:
        raise ValueError(f"Invalid 'user_dict_min_weight': {udw}")

    return out


def _read_and_merge(path: str, default_config: dict, debug: bool = False) -> bool:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        try:
            cfg = json.loads(raw)
        except json.JSONDecodeError:
            try:
                sanitized = _sanitize_json_text(raw)
                cfg = json.loads(sanitized)
                if debug:
                    print(f"⚠️  Config {path} contained comments/trailing commas — sanitized")
            except json.JSONDecodeError as e:
                if debug:
                    print(f"⚠️  JSON parse error in {path}: {e}")
                return False
        try:
            validated = validate_config(cfg)
            # Only override keys that were explicitly present in the source file
            for k in cfg.keys():
                if k in validated:
                    default_config[k] = validated[k]
            if debug:
                print(f"✓ Config loaded and validated: {path}")
            return True
        except ValueError as verr:
            if debug:
                print(f"⚠️  Invalid config {path}: {verr}")
    except Exception:
        return False
    return False


def load_config(config_path: str, debug: bool = False) -> dict:
    """Load and merge configuration from system and user paths.

    Returns the effective configuration dict (including `_config_path` and `_user_config_path` keys).
    """
    default_config = {
        'double_click_timeout': 0.3,
        'debug': False,
        'switch_layout_after_convert': True,
        'layout_switch_key': 'Alt_L+Shift_L',
        'auto_switch': False
    }

    # Try explicit path
    if config_path:
        _read_and_merge(config_path, default_config, debug=debug)

    # user config override
    user_cfg = os.path.expanduser('~/.config/lswitch/config.json')
    if os.path.exists(user_cfg):
        _read_and_merge(user_cfg, default_config, debug=debug)

    default_config['_config_path'] = config_path
    default_config['_user_config_path'] = user_cfg if os.path.exists(user_cfg) else None
    return default_config
