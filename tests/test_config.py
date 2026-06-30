"""Tests for lswitch.config — TOML loading, validation, ConfigManager."""

from __future__ import annotations

import pytest

from lswitch.config import (
    DEFAULT_CONFIG,
    DEFAULT_CONFIG_PATH,
    DEFAULT_TIMING,
    DEFAULT_WAYLAND_SELECTION_TIMING,
    DEFAULT_WAYLAND_TIMING,
    DEFAULT_X11_SELECTION_TIMING,
    WAYLAND_SELECTION_STRATEGIES,
    ConfigManager,
    load_config,
    validate_config,
)


# ------------------------------------------------------------------
# DEFAULT_CONFIG
# ------------------------------------------------------------------

class TestDefaultConfig:
    """DEFAULT_CONFIG contains all expected keys with correct types."""

    EXPECTED_KEYS = {
        'double_click_timeout',
        'debug',
        'switch_layout_after_convert',
        'layout_switch_key',
        'auto_switch',
        'auto_switch_threshold',
        'user_dict_enabled',
        'user_dict_min_weight',
        'wayland_selection_strategy',
        'timing',
        'x11_selection_timing',
        'wayland_timing',
        'wayland_selection_timing',
    }

    def test_contains_all_expected_keys(self):
        assert set(DEFAULT_CONFIG.keys()) == self.EXPECTED_KEYS
        assert DEFAULT_CONFIG['timing'] == DEFAULT_TIMING
        assert DEFAULT_CONFIG['x11_selection_timing'] == DEFAULT_X11_SELECTION_TIMING
        assert DEFAULT_CONFIG['wayland_timing'] == DEFAULT_WAYLAND_TIMING
        assert DEFAULT_CONFIG['wayland_selection_timing'] == DEFAULT_WAYLAND_SELECTION_TIMING


# ------------------------------------------------------------------
# validate_config
# ------------------------------------------------------------------

class TestValidateConfig:
    """validate_config normalises input and rejects invalid values."""

    def test_valid_data_passes(self):
        result = validate_config({
            'double_click_timeout': 0.5,
            'debug': True,
            'switch_layout_after_convert': False,
            'layout_switch_key': 'Caps_Lock',
            'auto_switch': True,
            'auto_switch_threshold': 5,
            'user_dict_enabled': True,
            'user_dict_min_weight': 3,
            'wayland_selection_strategy': 'clipboard_copy',
            'timing': {'key_press_delay': 0.002},
            'x11_selection_timing': {'paste_delay': 0.03},
            'wayland_timing': {'wl_clipboard_timeout': 2.0},
            'wayland_selection_timing': {'restore_delay': 0.2},
        })
        assert result['double_click_timeout'] == 0.5
        assert result['debug'] is True
        assert result['auto_switch_threshold'] == 5
        assert result['wayland_selection_strategy'] == 'clipboard_copy'
        assert result['timing']['key_press_delay'] == 0.002
        assert result['timing']['key_repeat_delay'] == DEFAULT_TIMING['key_repeat_delay']
        assert result['x11_selection_timing']['paste_delay'] == 0.03
        assert result['wayland_timing']['wl_clipboard_timeout'] == 2.0
        assert result['wayland_selection_timing']['restore_delay'] == 0.2

    def test_invalid_double_click_timeout_type(self):
        with pytest.raises(ValueError, match="double_click_timeout"):
            validate_config({'double_click_timeout': 'abc'})

    def test_invalid_double_click_timeout_range(self):
        with pytest.raises(ValueError, match="double_click_timeout"):
            validate_config({'double_click_timeout': 999})

    def test_invalid_debug_type(self):
        with pytest.raises(ValueError, match="debug"):
            validate_config({'debug': 'yes'})

    def test_invalid_layout_switch_key_empty(self):
        with pytest.raises(ValueError, match="layout_switch_key"):
            validate_config({'layout_switch_key': ''})

    def test_invalid_auto_switch_threshold_negative(self):
        with pytest.raises(ValueError, match="auto_switch_threshold"):
            validate_config({'auto_switch_threshold': -1})

    def test_invalid_wayland_selection_strategy(self):
        with pytest.raises(ValueError, match="wayland_selection_strategy"):
            validate_config({'wayland_selection_strategy': 'magic'})

    def test_invalid_timing_negative(self):
        with pytest.raises(ValueError, match="timing.key_press_delay"):
            validate_config({'timing': {'key_press_delay': -0.1}})

    def test_invalid_timing_unknown_key(self):
        with pytest.raises(ValueError, match="unknown keys"):
            validate_config({'wayland_selection_timing': {'mystery_delay': 1.0}})

    def test_wayland_selection_strategy_values_are_documented_set(self):
        assert WAYLAND_SELECTION_STRATEGIES == {
            "auto",
            "clipboard_copy",
            "primary_selection",
            "disabled",
        }

    def test_none_returns_defaults(self):
        result = validate_config(None)
        assert result == DEFAULT_CONFIG

    def test_empty_dict_returns_defaults(self):
        result = validate_config({})
        assert result == DEFAULT_CONFIG


# ------------------------------------------------------------------
# load_config
# ------------------------------------------------------------------

class TestLoadConfig:
    """load_config reads TOML files and merges with defaults."""

    def test_nonexistent_file_returns_defaults(self, tmp_path):
        result = load_config(config_path=str(tmp_path / "nope.toml"))
        assert result == DEFAULT_CONFIG

    def test_loads_real_toml_file(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            """
            # TOML comments are supported
            debug = true
            double_click_timeout = 0.5
            wayland_selection_strategy = "primary_selection"

            [timing]
            key_press_delay = 0.002

            [x11_selection_timing]
            poll_interval = 0.25

            [wayland_timing]
            wl_clipboard_timeout = 2.0

            [wayland_selection_timing]
            paste_delay = 0.15
            """,
            encoding="utf-8",
        )
        result = load_config(config_path=str(cfg_file))
        assert result['debug'] is True
        assert result['double_click_timeout'] == 0.5
        assert result['wayland_selection_strategy'] == 'primary_selection'
        assert result['timing']['key_press_delay'] == 0.002
        assert result['x11_selection_timing']['poll_interval'] == 0.25
        assert result['wayland_timing']['wl_clipboard_timeout'] == 2.0
        assert result['wayland_selection_timing']['paste_delay'] == 0.15
        # Other keys remain default
        assert result['auto_switch'] is False

    def test_invalid_toml_returns_defaults(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("debug = true\nbroken = [", encoding="utf-8")

        result = load_config(config_path=str(cfg_file), debug=True)

        assert result == DEFAULT_CONFIG

    def test_no_path_uses_toml_default(self):
        result = load_config(config_path=None)
        for key in DEFAULT_CONFIG:
            assert key in result
        assert DEFAULT_CONFIG_PATH.endswith("config.toml")


# ------------------------------------------------------------------
# ConfigManager
# ------------------------------------------------------------------

class TestConfigManager:
    """ConfigManager get/set/update/get_all/save/reload/reset."""

    def test_get_returns_default(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        assert mgr.get('double_click_timeout') == 0.3

    def test_get_missing_key_returns_default(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        assert mgr.get('nonexistent', 42) == 42

    def test_set_changes_value(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        mgr.set('debug', True)
        assert mgr.get('debug') is True

    def test_update_multiple(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        mgr.update({'debug': True, 'auto_switch': True})
        assert mgr.get('debug') is True
        assert mgr.get('auto_switch') is True

    def test_get_all_excludes_internal(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        mgr._config['_internal'] = 'secret'
        all_cfg = mgr.get_all()
        assert '_internal' not in all_cfg
        assert 'debug' in all_cfg

    def test_save_and_reload_roundtrip(self, tmp_path):
        cfg_path = str(tmp_path / "cfg.toml")
        mgr = ConfigManager(config_path=cfg_path)
        mgr.set('debug', True)
        mgr.set('double_click_timeout', 0.7)
        assert mgr.save() is True

        saved = (tmp_path / "cfg.toml").read_text(encoding="utf-8")
        assert "# Wayland selection strategies:" in saved
        assert "# Common input/conversion timings, seconds." in saved
        assert "[timing]" in saved
        assert "[x11_selection_timing]" in saved
        assert "[wayland_timing]" in saved
        assert "[wayland_selection_timing]" in saved
        assert 'debug = true' in saved
        assert 'double_click_timeout = 0.7' in saved

        # Reload
        mgr2 = ConfigManager(config_path=cfg_path)
        assert mgr2.get('debug') is True
        assert mgr2.get('double_click_timeout') == 0.7

    def test_reload_restores_from_file(self, tmp_path):
        cfg_path = str(tmp_path / "cfg.toml")
        mgr = ConfigManager(config_path=cfg_path)
        mgr.set('debug', True)
        mgr.save()
        # Mutate in-memory
        mgr.set('debug', False)
        assert mgr.get('debug') is False
        # Reload from disk
        assert mgr.reload() is True
        assert mgr.get('debug') is True

    def test_reset_to_defaults(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        mgr.set('debug', True)
        mgr.set('auto_switch', True)
        mgr.reset_to_defaults()
        assert mgr.get('debug') is False
        assert mgr.get('auto_switch') is False
        assert mgr.get_all() == DEFAULT_CONFIG

    def test_validate_with_valid_config(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        assert mgr.validate() is True

    def test_validate_with_invalid_config(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        mgr.set('double_click_timeout', 'bad')
        assert mgr.validate() is False

    def test_config_path_property(self, tmp_path):
        path = str(tmp_path / "cfg.toml")
        mgr = ConfigManager(config_path=path)
        assert mgr.config_path == path
