"""TOML configuration loader and validator for LSwitch 2.0.

The user config lives at ``~/.config/lswitch/config.toml``.  JSON config
compatibility is intentionally not supported.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - guarded by python_requires
    tomllib = None

logger = logging.getLogger(__name__)

CONFIG_DIR = os.path.expanduser("~/.config/lswitch")
DEFAULT_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.toml")
LEGACY_CONFIG_FILENAME = "config.json"
WAYLAND_SELECTION_STRATEGIES = {
    "auto",
    "clipboard_copy",
    "primary_selection",
    "disabled",
}


@dataclass(frozen=True)
class ConfigSnapshot:
    """Owned immutable-by-contract snapshot of normalized config values."""

    _values: dict = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_values", copy.deepcopy(self._values))

    def to_dict(self) -> dict:
        """Return a deep mutable copy suitable for a settings draft."""
        return copy.deepcopy(self._values)

    def get(self, key: str, default=None):
        """Read a value without exposing nested mutable state."""
        return copy.deepcopy(self._values.get(key, default))


@dataclass(frozen=True)
class ConfigChangeSet:
    """Validated transition between two complete config snapshots."""

    old: ConfigSnapshot
    new: ConfigSnapshot
    changed_paths: frozenset[str]
    source: str = "unknown"


class ConfigConflictError(RuntimeError):
    """Raised when a prepared update targets a stale config snapshot."""


_MISSING = object()


def diff_config_paths(old: dict, new: dict) -> frozenset[str]:
    """Return changed leaf paths using dotted TOML-style names."""
    changed: set[str] = set()

    def add_leaves(value, prefix: str) -> None:
        if isinstance(value, dict) and value:
            for key, child in value.items():
                add_leaves(child, f"{prefix}.{key}" if prefix else str(key))
            return
        if prefix:
            changed.add(prefix)

    def visit(left: dict, right: dict, prefix: str = "") -> None:
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else str(key)
            left_value = left.get(key, _MISSING)
            right_value = right.get(key, _MISSING)
            if left_value is _MISSING:
                add_leaves(right_value, path)
            elif right_value is _MISSING:
                add_leaves(left_value, path)
            elif isinstance(left_value, dict) and isinstance(right_value, dict):
                visit(left_value, right_value, path)
            elif left_value != right_value:
                changed.add(path)

    visit(old, new)
    return frozenset(changed)

DEFAULT_TIMING: dict[str, float] = {
    'key_press_delay': 0.001,
    'key_repeat_delay': 0.001,
    'retype_before_replay_delay': 0.05,
    'direct_type_after_layout_switch_delay': 0.03,
    'undo_before_replay_delay': 0.03,
    'auto_before_replay_delay': 0.03,
    'auto_before_space_delay': 0.01,
}

DEFAULT_X11_SELECTION_TIMING: dict[str, float] = {
    'poll_interval': 0.5,
    'paste_delay': 0.02,
    'restore_delay': 0.05,
    'expand_selection_delay': 0.05,
}

DEFAULT_WAYLAND_TIMING: dict[str, float] = {
    'wl_clipboard_timeout': 1.0,
}

DEFAULT_WAYLAND_SELECTION_TIMING: dict[str, float] = {
    'copy_wait_timeout': 1.0,
    'copy_poll_interval': 0.05,
    'copy_retry_delay': 0.1,
    'paste_delay': 0.12,
    'restore_delay': 0.15,
    'expand_selection_delay': 0.2,
}

# Single source of truth for default configuration
DEFAULT_CONFIG: dict = {
    'double_click_timeout': 0.3,
    'debug': False,
    'switch_layout_after_convert': True,
    'layout_switch_key': 'Alt+Shift',
    'auto_switch': False,
    'auto_switch_threshold': 0,
    'auto_switch_mid_word': False,
    'mid_word_min_prefix_len': 4,
    'system_dict_enabled': True,
    'system_dict_en_path': '',
    'system_dict_ru_path': '',
    'user_dict_enabled': False,
    'user_dict_auto_confirm': False,
    'user_dict_min_weight': 2,
    'wayland_selection_strategy': 'auto',
    'timing': DEFAULT_TIMING,
    'x11_selection_timing': DEFAULT_X11_SELECTION_TIMING,
    'wayland_timing': DEFAULT_WAYLAND_TIMING,
    'wayland_selection_timing': DEFAULT_WAYLAND_SELECTION_TIMING,
}

_CONFIG_KEY_ORDER = tuple(
    key for key, value in DEFAULT_CONFIG.items()
    if not isinstance(value, dict)
)
_CONFIG_SECTION_ORDER = (
    'timing',
    'x11_selection_timing',
    'wayland_timing',
    'wayland_selection_timing',
)
_CONFIG_SECTION_KEY_ORDER = {
    key: tuple(value.keys())
    for key, value in DEFAULT_CONFIG.items()
    if isinstance(value, dict)
}

_CONFIG_COMMENTS: dict[str, str] = {
    'double_click_timeout': 'Maximum interval between two Shift presses, seconds.',
    'debug': 'Enable verbose logging and Debug Monitor tray action.',
    'switch_layout_after_convert': 'Switch keyboard layout after manual conversion.',
    'layout_switch_key': 'Shortcut used by the system to switch keyboard layout.',
    'auto_switch': 'Enable automatic wrong-layout detection and conversion.',
    'auto_switch_threshold': 'Minimum detector confidence for automatic conversion.',
    'auto_switch_mid_word': 'Enable layout switching while a word is still being typed.',
    'mid_word_min_prefix_len': 'Minimum prefix length before mid-word detection starts.',
    'system_dict_enabled': 'Use system Hunspell/MySpell dictionaries when available.',
    'system_dict_en_path': 'Optional explicit English Hunspell/MySpell .dic path.',
    'system_dict_ru_path': 'Optional explicit Russian Hunspell/MySpell .dic path.',
    'user_dict_enabled': 'Enable the self-learning user dictionary.',
    'user_dict_auto_confirm': 'Automatically confirm accepted auto-conversions in the user dictionary.',
    'user_dict_min_weight': 'Minimum user dictionary score required to affect detection.',
    'wayland_selection_strategy': 'Wayland selection conversion mode.',
    'timing': 'Common input/conversion timings, seconds.',
    'timing.key_press_delay': 'Delay between virtual key press and release.',
    'timing.key_repeat_delay': 'Delay between successive virtual key taps.',
    'timing.retype_before_replay_delay': 'After layout switch before replaying typed word.',
    'timing.direct_type_after_layout_switch_delay': 'After layout switch before direct selection typing.',
    'timing.undo_before_replay_delay': 'After layout switch before undo replay.',
    'timing.auto_before_replay_delay': 'After layout switch before auto-conversion replay.',
    'timing.auto_before_space_delay': 'After auto-conversion replay before final Space handling.',
    'x11_selection_timing': 'X11-only selection timings, seconds.',
    'x11_selection_timing.poll_interval': 'PRIMARY selection polling interval.',
    'x11_selection_timing.paste_delay': 'After writing clipboard before Ctrl+V.',
    'x11_selection_timing.restore_delay': 'After Ctrl+V before restoring clipboard.',
    'x11_selection_timing.expand_selection_delay': 'After Ctrl+Shift+Left before reading PRIMARY.',
    'wayland_timing': 'Wayland-only system timings, seconds.',
    'wayland_timing.wl_clipboard_timeout': 'Timeout for wl-copy/wl-paste helper commands.',
    'wayland_selection_timing': 'Wayland-only selection timings, seconds.',
    'wayland_selection_timing.copy_wait_timeout': 'Maximum wait for Ctrl+C to update clipboard.',
    'wayland_selection_timing.copy_poll_interval': 'Clipboard poll interval after copy shortcut.',
    'wayland_selection_timing.copy_retry_delay': 'Delay before trying fallback copy shortcut.',
    'wayland_selection_timing.paste_delay': 'After writing clipboard before Ctrl+V.',
    'wayland_selection_timing.restore_delay': 'After Ctrl+V before restoring clipboard.',
    'wayland_selection_timing.expand_selection_delay': 'After Ctrl+Shift+Left before reading selection.',
}


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
            comment = _CONFIG_COMMENTS.get(key)
            if comment:
                lines.append(f"# {comment}")
            lines.append(f"{key} = {_toml_value(config[key])}")

    for section in _CONFIG_SECTION_ORDER:
        values = config.get(section)
        if not isinstance(values, dict):
            continue
        lines.append("")
        comment = _CONFIG_COMMENTS.get(section)
        if comment:
            lines.append(f"# {comment}")
        lines.append(f"[{section}]")
        key_order = _CONFIG_SECTION_KEY_ORDER.get(section, tuple(values.keys()))
        for child_key in key_order:
            if child_key not in values:
                continue
            child_comment = _CONFIG_COMMENTS.get(f"{section}.{child_key}")
            if child_comment:
                lines.append(f"# {child_comment}")
            lines.append(f"{child_key} = {_toml_value(values[child_key])}")

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


def _normalize_config_path(config_path: str | None = None) -> str:
    """Return the TOML config path; never write legacy ``config.json``."""
    if not config_path:
        return DEFAULT_CONFIG_PATH

    if os.path.basename(config_path) == LEGACY_CONFIG_FILENAME:
        return os.path.join(os.path.dirname(config_path), "config.toml")

    return config_path


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

    defaults = copy.deepcopy(DEFAULT_CONFIG)
    out = copy.deepcopy(defaults)

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

    # layout_switch_key — validated canonical shortcut
    lsk = conf.get('layout_switch_key', defaults['layout_switch_key'])
    try:
        from lswitch.core.layout_switch_controller import normalize_key_sequence

        out['layout_switch_key'] = normalize_key_sequence(lsk)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid 'layout_switch_key': {exc}") from exc

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

    # auto_switch_mid_word — boolean
    asmw = conf.get('auto_switch_mid_word', defaults['auto_switch_mid_word'])
    if not isinstance(asmw, bool):
        raise ValueError("Invalid 'auto_switch_mid_word': must be boolean")
    out['auto_switch_mid_word'] = asmw

    # mid_word_min_prefix_len — positive int
    mw_min_raw = conf.get(
        'mid_word_min_prefix_len',
        defaults['mid_word_min_prefix_len'],
    )
    try:
        mw_min_i = int(mw_min_raw)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid 'mid_word_min_prefix_len': {mw_min_raw}")
    if not (1 <= mw_min_i <= 32):
        raise ValueError(
            "Invalid 'mid_word_min_prefix_len': must be between 1 and 32"
        )
    out['mid_word_min_prefix_len'] = mw_min_i

    # system_dict_enabled — boolean
    sde = conf.get('system_dict_enabled', defaults['system_dict_enabled'])
    if not isinstance(sde, bool):
        raise ValueError("Invalid 'system_dict_enabled': must be boolean")
    out['system_dict_enabled'] = sde

    # system_dict_*_path — optional string paths
    for key in ('system_dict_en_path', 'system_dict_ru_path'):
        path_value = conf.get(key, defaults[key])
        if not isinstance(path_value, str):
            raise ValueError(f"Invalid '{key}': must be a string")
        out[key] = path_value

    # user_dict_enabled — boolean
    ude = conf.get('user_dict_enabled', defaults['user_dict_enabled'])
    if not isinstance(ude, bool):
        raise ValueError("Invalid 'user_dict_enabled': must be boolean")
    out['user_dict_enabled'] = ude

    # user_dict_auto_confirm — boolean
    udac = conf.get('user_dict_auto_confirm', defaults['user_dict_auto_confirm'])
    if not isinstance(udac, bool):
        raise ValueError("Invalid 'user_dict_auto_confirm': must be boolean")
    out['user_dict_auto_confirm'] = udac

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

    out['timing'] = _validate_timing_table(
        conf,
        'timing',
        defaults['timing'],
    )
    out['x11_selection_timing'] = _validate_timing_table(
        conf,
        'x11_selection_timing',
        defaults['x11_selection_timing'],
    )
    out['wayland_timing'] = _validate_timing_table(
        conf,
        'wayland_timing',
        defaults['wayland_timing'],
    )
    out['wayland_selection_timing'] = _validate_timing_table(
        conf,
        'wayland_selection_timing',
        defaults['wayland_selection_timing'],
    )

    return out


def _validate_timing_table(
    conf: dict,
    section: str,
    defaults: dict[str, float],
) -> dict[str, float]:
    raw = conf.get(section, {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid '{section}': must be a TOML table")

    unknown = sorted(key for key in raw if key not in defaults)
    if unknown:
        raise ValueError(
            f"Invalid '{section}': unknown keys {unknown}"
        )

    out: dict[str, float] = {}
    for key, default_value in defaults.items():
        value = raw.get(key, default_value)
        if isinstance(value, bool):
            raise ValueError(f"Invalid '{section}.{key}': must be a number")
        try:
            f_value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid '{section}.{key}': {value}")
        if not (0.0 <= f_value <= 30.0):
            raise ValueError(
                f"Invalid '{section}.{key}': must be between 0.0 and 30.0"
            )
        out[key] = f_value
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


def _config_file_missing_defaults(path: str, debug: bool = False) -> bool:
    """Return True when an existing TOML file lacks known default keys."""
    try:
        cfg = _load_toml(path)
    except Exception as exc:
        if debug:
            logger.warning("TOML parse error in %s: %s", path, exc)
        return False

    for key, default_value in DEFAULT_CONFIG.items():
        if key not in cfg:
            return True
        if isinstance(default_value, dict):
            section = cfg.get(key)
            if not isinstance(section, dict):
                return True
            for child_key in default_value:
                if child_key not in section:
                    return True
    return False


# ------------------------------------------------------------------
# Top-level loader
# ------------------------------------------------------------------

def load_config(config_path: str | None = None, debug: bool = False) -> dict:
    """Load and merge TOML configuration.

    If *config_path* is given, uses only that file.  Otherwise reads
    ``~/.config/lswitch/config.toml``.
    """
    default_config = copy.deepcopy(DEFAULT_CONFIG)
    path = _normalize_config_path(config_path)
    if os.path.exists(path):
        _read_and_merge(path, default_config, debug=debug)
    return default_config


# ------------------------------------------------------------------
# ConfigManager
# ------------------------------------------------------------------

class ConfigManager:
    """Centralized configuration management with load/save/validate."""

    def __init__(self, config_path: str | None = None, debug: bool = False):
        self._config_path = _normalize_config_path(config_path)
        self._debug = debug
        self._lock = threading.RLock()
        self._config: dict = copy.deepcopy(DEFAULT_CONFIG)
        self._load_config()

    # -- internal -------------------------------------------------------

    def _load_config(self) -> None:
        """Reset to defaults, then overlay from TOML file if it exists."""
        loaded_config = copy.deepcopy(DEFAULT_CONFIG)
        if self._config_path and os.path.exists(self._config_path):
            loaded = _read_and_merge(
                self._config_path,
                loaded_config,
                debug=self._debug,
            )
            with self._lock:
                self._config = loaded_config
            if loaded and _config_file_missing_defaults(
                self._config_path,
                debug=self._debug,
            ):
                self.save()
            return
        with self._lock:
            self._config = loaded_config

    # -- public ---------------------------------------------------------

    @property
    def config_path(self) -> str:
        return self._config_path

    def reload(self) -> bool:
        """Reload configuration from file. Returns True on success."""
        try:
            self._load_config()
            return True
        except Exception:
            return False

    def read_candidate(self, source_path: str | None = None) -> dict:
        """Strictly read and normalize a config file without mutating state."""
        path = source_path or self._config_path
        raw = _load_toml(path)
        return validate_config(raw)

    def save(self, target_path: str | None = None) -> bool:
        """Atomically save configuration to TOML. Returns True on success."""
        save_path = target_path or self._config_path
        try:
            with self._lock:
                candidate = {
                    key: copy.deepcopy(value)
                    for key, value in self._config.items()
                    if not key.startswith('_')
                }
            normalized = validate_config(candidate)
            _save_toml(save_path, normalized)
            with self._lock:
                self._config = copy.deepcopy(normalized)
            return True
        except Exception:
            return False

    def get(self, key: str, default=None):
        """Get a single configuration value."""
        with self._lock:
            return copy.deepcopy(self._config.get(key, default))

    def set_debug(self, enabled: bool) -> None:
        """Update diagnostic logging used by subsequent file reloads."""
        self._debug = bool(enabled)

    def set(self, key: str, value) -> None:
        """Set a single configuration value."""
        with self._lock:
            self._config[key] = copy.deepcopy(value)

    def update(self, updates: dict) -> None:
        """Update multiple configuration values."""
        with self._lock:
            self._config.update(copy.deepcopy(updates))

    def get_all(self) -> dict:
        """Return all configuration (excluding internal keys)."""
        return self.snapshot().to_dict()

    def snapshot(self) -> ConfigSnapshot:
        """Return an isolated snapshot of the current public configuration."""
        with self._lock:
            values = {
                key: copy.deepcopy(value)
                for key, value in self._config.items()
                if not key.startswith('_')
            }
        return ConfigSnapshot(values)

    def prepare_update(
        self,
        candidate: dict | ConfigSnapshot,
        *,
        source: str = "unknown",
    ) -> ConfigChangeSet:
        """Validate a complete candidate without mutating memory or disk."""
        raw = candidate.to_dict() if isinstance(candidate, ConfigSnapshot) else copy.deepcopy(candidate)
        normalized = validate_config(raw)
        old = self.snapshot()
        new = ConfigSnapshot(normalized)
        return ConfigChangeSet(
            old=old,
            new=new,
            changed_paths=diff_config_paths(old.to_dict(), new.to_dict()),
            source=source,
        )

    def commit_update(
        self,
        change_set: ConfigChangeSet,
        *,
        persist: bool = True,
        target_path: str | None = None,
    ) -> None:
        """Commit a prepared update atomically or raise without mutation."""
        save_path = target_path or self._config_path
        with self._lock:
            current = ConfigSnapshot({
                key: copy.deepcopy(value)
                for key, value in self._config.items()
                if not key.startswith('_')
            })
            if current != change_set.old:
                raise ConfigConflictError(
                    "Configuration changed after this update was prepared"
                )
            new_values = change_set.new.to_dict()
            if persist:
                _save_toml(save_path, new_values)
            self._config = new_values

    def replace(
        self,
        candidate: dict | ConfigSnapshot,
        *,
        source: str = "unknown",
        persist: bool = True,
    ) -> ConfigChangeSet:
        """Validate and commit a complete candidate in one operation."""
        change_set = self.prepare_update(candidate, source=source)
        self.commit_update(change_set, persist=persist)
        return change_set

    def reset_to_defaults(self) -> None:
        """Reset configuration to DEFAULT_CONFIG."""
        with self._lock:
            self._config = copy.deepcopy(DEFAULT_CONFIG)

    def validate(self) -> bool:
        """Validate current configuration. Returns True if valid."""
        try:
            validate_config(self.snapshot().to_dict())
            return True
        except ValueError:
            return False

    @property
    def config_path(self) -> str:
        """Current config file path."""
        return self._config_path
