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

# Single source of truth for default configuration
DEFAULT_CONFIG = {
    'double_click_timeout': 0.3,
    'debug': False,
    'switch_layout_after_convert': True,
    'layout_switch_key': 'Alt_L+Shift_L',
    'auto_switch': False,
    'auto_switch_threshold': 10,
    'user_dict_enabled': False,
    'user_dict_min_weight': 2,
}


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

    defaults = dict(DEFAULT_CONFIG)

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

    # auto_switch_threshold
    ast = conf.get('auto_switch_threshold', defaults['auto_switch_threshold'])
    try:
        ast_i = int(ast)
        if ast_i < 0:
            raise ValueError('auto_switch_threshold must be >= 0')
        out['auto_switch_threshold'] = ast_i
    except Exception:
        raise ValueError(f"Invalid 'auto_switch_threshold': {ast}")

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
    default_config = dict(DEFAULT_CONFIG)

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


class ConfigManager:
    """Централизованное управление конфигурацией."""
    
    def __init__(self, config_path: str | None = None, debug: bool = False):
        """Initialize ConfigManager.
        
        Args:
            config_path: Path to config file. If None, auto-detects.
            debug: Enable debug logging.
        """
        self._config_path = config_path or self._detect_config_path()
        self._debug = debug
        self._config = dict(DEFAULT_CONFIG)
        self._load_config()
    
    def _detect_config_path(self) -> str:
        """Auto-detect configuration file path with priority order."""
        user_config = os.path.expanduser('~/.config/lswitch/config.json')
        system_config = '/etc/lswitch/config.json'
        
        if os.path.exists(system_config):
            return system_config
        elif os.path.exists(user_config):
            return user_config
        else:
            return user_config  # Will be created when saving
    
    def _load_config(self) -> None:
        """Load and merge configuration from file and user paths."""
        # Reset to defaults
        self._config = dict(DEFAULT_CONFIG)
        
        # Try explicit path
        if self._config_path and os.path.exists(self._config_path):
            _read_and_merge(self._config_path, self._config, debug=self._debug)
        
        # User config override (from ~/.config/lswitch/config.json)
        user_cfg = os.path.expanduser('~/.config/lswitch/config.json')
        if os.path.exists(user_cfg):
            _read_and_merge(user_cfg, self._config, debug=self._debug)
    
    def reload(self) -> bool:
        """Reload configuration from file.
        
        Returns:
            True if reload successful, False otherwise.
        """
        try:
            self._load_config()
            return True
        except Exception as e:
            if self._debug:
                print(f"⚠️ Failed to reload config: {e}")
            return False
    
    def save(self, target_path: str | None = None) -> bool:
        """Save configuration to file.
        
        Args:
            target_path: Path to save to. If None, uses current config_path.
            
        Returns:
            True if save successful, False otherwise.
        """
        save_path = target_path or self._config_path
        
        try:
            os.makedirs(os.path.dirname(save_path) or '.', exist_ok=True)
            with open(save_path, 'w', encoding='utf-8') as f:
                # Filter out internal keys when saving
                save_data = {k: v for k, v in self._config.items()
                            if not k.startswith('_')}
                json.dump(save_data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            if self._debug:
                print(f"⚠️ Failed to save config to {save_path}: {e}")
            return False
    
    def get(self, key: str, default: any = None) -> any:
        """Get configuration value.
        
        Args:
            key: Configuration key.
            default: Default value if key not found.
            
        Returns:
            Configuration value or default.
        """
        return self._config.get(key, default)
    
    def set(self, key: str, value: any) -> None:
        """Set configuration value.
        
        Args:
            key: Configuration key.
            value: Value to set.
        """
        self._config[key] = value
    
    def update(self, updates: dict[str, any]) -> None:
        """Update multiple configuration values.
        
        Args:
            updates: Dictionary of key-value pairs to update.
        """
        self._config.update(updates)
    
    def get_all(self) -> dict[str, any]:
        """Get all configuration as dictionary.
        
        Returns:
            Copy of current configuration (excluding internal keys).
        """
        return {k: v for k, v in self._config.items()
                if not k.startswith('_')}
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to default values."""
        self._config = dict(DEFAULT_CONFIG)
    
    def validate(self) -> bool:
        """Validate current configuration.
        
        Returns:
            True if configuration is valid, False otherwise.
        """
        try:
            validate_config(self._config)
            return True
        except ValueError as e:
            if self._debug:
                print(f"⚠️ Config validation failed: {e}")
            return False
    
    @property
    def config_path(self) -> str:
        """Get current config file path."""
        return self._config_path
    
    @config_path.setter
    def config_path(self, path: str) -> None:
        """Set config file path and reload."""
        self._config_path = path
        self.reload()
