"""TOML configuration loader and validator for LSwitch 2.0.

The user config lives at ``~/.config/lswitch/config.toml``.  JSON config
compatibility is intentionally not supported.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - guarded by python_requires
    tomllib = None

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.expanduser("~/.config/lswitch")
DEFAULT_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.toml")
WAYLAND_SELECTION_STRATEGIES = {
    "auto",
    "clipboard_copy",
    "primary_selection",
    "disabled",
}

# Single source of truth for default configuration
DEFAULT_CONFIG: dict = {
    'double_click_timeout': 0.3,
    'debug': False,
    'switch_layout_after_convert': True,
    'layout_switch_key': 'Alt_L+Shift_L',
    'auto_switch': False,
    'auto_switch_threshold': 0,
    'user_dict_enabled': False,
    'user_dict_min_weight': 2,
    'wayland_selection_strategy': 'auto',
}

_CONFIG_KEY_ORDER = tuple(DEFAULT_CONFIG.keys())


# ------------------------------------------------------------------
# TOML IO
# ------------------------------------------------------------------

def _load_toml(path: str) -> dict:
    if tomllib is None:
        raise RuntimeError("TOML config requires Python 3.11+")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    if not isinstance(data, dict):
        raise ValueError("TOML config root must be a table")
    return data


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"Unsupported TOML value type: {type(value).__name__}")


def _dump_config_toml(config: dict) -> str:
    lines = [
        "# LSwitch configuration",
        "#",
        "# Wayland selection strategies:",
        "#   auto              - read PRIMARY selection first, fallback to clipboard copy/paste",
        "#   clipboard_copy    - always use clipboard copy/paste flow",
        "#   primary_selection - read PRIMARY and replace selection by direct UInput typing",
        "#   disabled          - disable Wayland selection conversion",
        "",
    ]

    for key in _CONFIG_KEY_ORDER:
        if key in config:
            lines.append(f"{key} = {_toml_value(config[key])}")

    extra_keys = sorted(
        key for key in config
        if key not in DEFAULT_CONFIG and not key.startswith("_")
    )
    if extra_keys:
        lines.append("")
    for key in extra_keys:
        value = config[key]
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for child_key in sorted(value):
                lines.append(f"{child_key} = {_toml_value(value[child_key])}")
            lines.append("")
        else:
            lines.append(f"{key} = {_toml_value(value)}")

    return "\n".join(lines).rstrip() + "\n"


def _save_toml(path: str, config: dict) -> None:
    dir_path = os.path.dirname(os.path.abspath(path))
    os.makedirs(dir_path, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".toml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_dump_config_toml(config))
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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

    # wayland_selection_strategy — advanced Wayland selection strategy
    wss = conf.get('wayland_selection_strategy', defaults['wayland_selection_strategy'])
    if wss not in WAYLAND_SELECTION_STRATEGIES:
        raise ValueError(
            "Invalid 'wayland_selection_strategy': "
            f"must be one of {sorted(WAYLAND_SELECTION_STRATEGIES)}"
        )
    out['wayland_selection_strategy'] = wss

    return out


def _read_and_merge(path: str, target_config: dict, debug: bool = False) -> bool:
    """Read a TOML file, validate it, and merge known keys."""
    try:
        cfg = _load_toml(path)
    except Exception as exc:
        if debug:
            logger.warning("TOML parse error in %s: %s", path, exc)
        return False

    try:
        validated = validate_config(cfg)
        # Only override keys explicitly present in source
        for key in cfg:
            if key in validated:
                target_config[key] = validated[key]
        return True
    except ValueError as verr:
        if debug:
            logger.warning("Invalid config %s: %s", path, verr)
        return False


# ------------------------------------------------------------------
# Top-level loader
# ------------------------------------------------------------------

def load_config(config_path: str | None = None, debug: bool = False) -> dict:
    """Load and merge TOML configuration.

    If *config_path* is given, uses only that file.  Otherwise reads
    ``~/.config/lswitch/config.toml``.
    """
    default_config = dict(DEFAULT_CONFIG)
    path = config_path or DEFAULT_CONFIG_PATH
    if os.path.exists(path):
        _read_and_merge(path, default_config, debug=debug)
    return default_config


# ------------------------------------------------------------------
# ConfigManager
# ------------------------------------------------------------------

class ConfigManager:
    """Centralized configuration management with load/save/validate."""

    def __init__(self, config_path: str | None = None, debug: bool = False):
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        self._debug = debug
        self._config: dict = dict(DEFAULT_CONFIG)
        self._load_config()

    # -- internal -------------------------------------------------------

    def _load_config(self) -> None:
        """Reset to defaults, then overlay from TOML file if it exists."""
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
        """Atomically save configuration to TOML. Returns True on success."""
        save_path = target_path or self._config_path
        try:
            save_data = {k: v for k, v in self._config.items() if not k.startswith('_')}
            _save_toml(save_path, save_data)
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
