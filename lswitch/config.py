"""Configuration loader and validator for LSwitch 2.0.

Provides ``load_config(path)`` which reads a JSON config (with
comment and trailing-comma tolerant sanitizer) and merges user
overrides from ``~/.config/lswitch/config.json``.

Also provides ``validate_config(conf)`` which normalizes and
validates config keys, raising ``ValueError`` on invalid values.
"""

from __future__ import annotations

import json
import logging
import os

from lswitch.intelligence.persistence import save_json

logger = logging.getLogger(__name__)

# Single source of truth for default configuration
DEFAULT_CONFIG: dict = {
    'double_click_timeout': 0.3,
    'debug': False,
    'switch_layout_after_convert': True,
    'layout_switch_key': 'Alt_L+Shift_L',
    'auto_switch': False,
    'auto_switch_threshold': 10,
    'user_dict_enabled': False,
    'user_dict_min_weight': 2,
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _sanitize_json_text(s: str) -> str:
    """Remove ``#``/``//`` comments and trailing commas from JSON-like text."""
    import re

    # Hash-style line comments
    s = re.sub(r"^[ \t]*#.*$", "", s, flags=re.MULTILINE)
    # C++-style line comments
    s = re.sub(r"//.*$", "", s, flags=re.MULTILINE)
    # Trailing commas before } or ]
    s = re.sub(r",[ \t\r\n]+(\}|\])", r"\1", s)
    return s


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------

def validate_config(conf: dict | None) -> dict:
    """Validate and normalize configuration dictionary.

    Returns a normalized dict with all expected keys.
    Raises ``ValueError`` on invalid values.
    """
    if conf is None:
        conf = {}

    defaults = dict(DEFAULT_CONFIG)
    out = dict(defaults)

    # double_click_timeout — positive float in [0.05, 10.0]
    dct = conf.get('double_click_timeout', defaults['double_click_timeout'])
    try:
        dct_val = float(dct)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid 'double_click_timeout': {dct}")
    if not (0.05 <= dct_val <= 10.0):
        raise ValueError(f"Invalid 'double_click_timeout': {dct} (must be between 0.05 and 10.0)")
    out['double_click_timeout'] = dct_val

    # debug — boolean
    dbg = conf.get('debug', defaults['debug'])
    if not isinstance(dbg, bool):
        raise ValueError("Invalid 'debug' flag: must be boolean")
    out['debug'] = dbg

    # switch_layout_after_convert — boolean
    sl = conf.get('switch_layout_after_convert', defaults['switch_layout_after_convert'])
    if not isinstance(sl, bool):
        raise ValueError("Invalid 'switch_layout_after_convert': must be boolean")
    out['switch_layout_after_convert'] = sl

    # layout_switch_key — non-empty string
    lsk = conf.get('layout_switch_key', defaults['layout_switch_key'])
    if not isinstance(lsk, str) or not lsk:
        raise ValueError("Invalid 'layout_switch_key': must be a non-empty string")
    out['layout_switch_key'] = lsk

    # auto_switch — boolean
    autos = conf.get('auto_switch', defaults['auto_switch'])
    if not isinstance(autos, bool):
        raise ValueError("Invalid 'auto_switch': must be boolean")
    out['auto_switch'] = autos

    # auto_switch_threshold — non-negative int
    ast_raw = conf.get('auto_switch_threshold', defaults['auto_switch_threshold'])
    try:
        ast_i = int(ast_raw)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid 'auto_switch_threshold': {ast_raw}")
    if ast_i < 0:
        raise ValueError(f"Invalid 'auto_switch_threshold': must be >= 0")
    out['auto_switch_threshold'] = ast_i

    # user_dict_enabled — boolean
    ude = conf.get('user_dict_enabled', defaults['user_dict_enabled'])
    if not isinstance(ude, bool):
        raise ValueError("Invalid 'user_dict_enabled': must be boolean")
    out['user_dict_enabled'] = ude

    # user_dict_min_weight — non-negative int
    udw = conf.get('user_dict_min_weight', defaults['user_dict_min_weight'])
    try:
        udw_i = int(udw)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid 'user_dict_min_weight': {udw}")
    if udw_i < 0:
        raise ValueError(f"Invalid 'user_dict_min_weight': must be >= 0")
    out['user_dict_min_weight'] = udw_i

    return out


def _read_and_merge(path: str, target_config: dict, debug: bool = False) -> bool:
    """Read a JSON file, validate, and merge into *target_config*.

    Returns True on success, False on any error.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
    except Exception:
        return False

    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError:
        try:
            sanitized = _sanitize_json_text(raw)
            cfg = json.loads(sanitized)
        except json.JSONDecodeError as exc:
            if debug:
                logger.warning("JSON parse error in %s: %s", path, exc)
            return False

    try:
        validated = validate_config(cfg)
        # Only override keys explicitly present in source
        for k in cfg:
            if k in validated:
                target_config[k] = validated[k]
        return True
    except ValueError as verr:
        if debug:
            logger.warning("Invalid config %s: %s", path, verr)
        return False


# ------------------------------------------------------------------
# Top-level loader
# ------------------------------------------------------------------

def load_config(config_path: str | None = None, debug: bool = False) -> dict:
    """Load and merge configuration.

    If *config_path* is given, uses only that file (returns defaults if
    the file does not exist).  Otherwise falls back to
    ``~/.config/lswitch/config.json``.

    Returns the effective configuration dict (always has all default keys).
    """
    default_config = dict(DEFAULT_CONFIG)

    if config_path is not None:
        # Explicit path — use only it, no fallback
        if os.path.exists(config_path):
            _read_and_merge(config_path, default_config, debug=debug)
        return default_config

    user_cfg = os.path.expanduser('~/.config/lswitch/config.json')
    if os.path.exists(user_cfg):
        _read_and_merge(user_cfg, default_config, debug=debug)

    return default_config


# ------------------------------------------------------------------
# ConfigManager
# ------------------------------------------------------------------

class ConfigManager:
    """Centralized configuration management with load/save/validate."""

    def __init__(self, config_path: str | None = None, debug: bool = False):
        self._config_path = config_path or os.path.expanduser('~/.config/lswitch/config.json')
        self._debug = debug
        self._config: dict = dict(DEFAULT_CONFIG)
        self._load_config()

    # -- internal -------------------------------------------------------

    def _load_config(self) -> None:
        """Reset to defaults, then overlay from file (if exists)."""
        self._config = dict(DEFAULT_CONFIG)
        if self._config_path and os.path.exists(self._config_path):
            _read_and_merge(self._config_path, self._config, debug=self._debug)

    # -- public ---------------------------------------------------------

    def reload(self) -> bool:
        """Reload configuration from file. Returns True on success."""
        try:
            self._load_config()
            return True
        except Exception:
            return False

    def save(self, target_path: str | None = None) -> bool:
        """Atomically save configuration to file. Returns True on success."""
        save_path = target_path or self._config_path
        try:
            save_data = {k: v for k, v in self._config.items() if not k.startswith('_')}
            save_json(save_path, save_data)
            return True
        except Exception:
            return False

    def get(self, key: str, default=None):
        """Get a single configuration value."""
        return self._config.get(key, default)

    def set(self, key: str, value) -> None:
        """Set a single configuration value."""
        self._config[key] = value

    def update(self, updates: dict) -> None:
        """Update multiple configuration values."""
        self._config.update(updates)

    def get_all(self) -> dict:
        """Return all configuration (excluding internal keys)."""
        return {k: v for k, v in self._config.items() if not k.startswith('_')}

    def reset_to_defaults(self) -> None:
        """Reset configuration to DEFAULT_CONFIG."""
        self._config = dict(DEFAULT_CONFIG)

    def validate(self) -> bool:
        """Validate current configuration. Returns True if valid."""
        try:
            validate_config(self._config)
            return True
        except ValueError:
            return False

    @property
    def config_path(self) -> str:
        """Current config file path."""
        return self._config_path
