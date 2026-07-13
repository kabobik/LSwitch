"""Tests for lswitch.config — TOML loading, validation, ConfigManager."""

from __future__ import annotations

import pytest

from lswitch.config import (
    ConfigConflictError,
    ConfigSnapshot,
    DEFAULT_CONFIG,
    DEFAULT_CONFIG_PATH,
    DEFAULT_TIMING,
    DEFAULT_WAYLAND_SELECTION_TIMING,
    DEFAULT_WAYLAND_TIMING,
    DEFAULT_X11_SELECTION_TIMING,
    WAYLAND_SELECTION_STRATEGIES,
    ConfigManager,
    diff_config_paths,
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
        'auto_switch_mid_word',
        'mid_word_min_prefix_len',
        'system_dict_enabled',
        'system_dict_en_path',
        'system_dict_ru_path',
        'user_dict_enabled',
        'user_dict_auto_confirm',
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
            'auto_switch_mid_word': True,
            'mid_word_min_prefix_len': 5,
            'system_dict_enabled': False,
            'system_dict_en_path': '/tmp/en_US.dic',
            'system_dict_ru_path': '/tmp/ru_RU.dic',
            'user_dict_enabled': True,
            'user_dict_auto_confirm': True,
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
        assert result['auto_switch_mid_word'] is True
        assert result['mid_word_min_prefix_len'] == 5
        assert result['system_dict_enabled'] is False
        assert result['system_dict_en_path'] == '/tmp/en_US.dic'
        assert result['system_dict_ru_path'] == '/tmp/ru_RU.dic'
        assert result['user_dict_auto_confirm'] is True
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

    def test_invalid_auto_switch_mid_word_type(self):
        with pytest.raises(ValueError, match="auto_switch_mid_word"):
            validate_config({'auto_switch_mid_word': 'yes'})

    def test_invalid_mid_word_min_prefix_len_range(self):
        with pytest.raises(ValueError, match="mid_word_min_prefix_len"):
            validate_config({'mid_word_min_prefix_len': 0})

    def test_invalid_system_dict_enabled_type(self):
        with pytest.raises(ValueError, match="system_dict_enabled"):
            validate_config({'system_dict_enabled': 'yes'})

    def test_invalid_system_dict_path_type(self):
        with pytest.raises(ValueError, match="system_dict_en_path"):
            validate_config({'system_dict_en_path': 123})

    def test_invalid_user_dict_auto_confirm_type(self):
        with pytest.raises(ValueError, match="user_dict_auto_confirm"):
            validate_config({'user_dict_auto_confirm': 'yes'})

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
            auto_switch_mid_word = true
            mid_word_min_prefix_len = 5
            system_dict_enabled = false
            system_dict_en_path = "/tmp/en_US.dic"
            system_dict_ru_path = "/tmp/ru_RU.dic"

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
        assert result['auto_switch_mid_word'] is True
        assert result['mid_word_min_prefix_len'] == 5
        assert result['system_dict_enabled'] is False
        assert result['system_dict_en_path'] == '/tmp/en_US.dic'
        assert result['system_dict_ru_path'] == '/tmp/ru_RU.dic'
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

    def test_get_all_is_deeply_isolated(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))

        draft = mgr.get_all()
        draft["timing"]["key_press_delay"] = 9.0

        assert mgr.get("timing")["key_press_delay"] == DEFAULT_CONFIG["timing"]["key_press_delay"]

    def test_get_nested_value_is_deeply_isolated(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))

        timing = mgr.get("timing")
        timing["key_repeat_delay"] = 8.0

        assert mgr.get("timing")["key_repeat_delay"] == DEFAULT_CONFIG["timing"]["key_repeat_delay"]

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
        assert 'auto_switch_mid_word = false' in saved
        assert 'mid_word_min_prefix_len = 4' in saved

        # Reload
        mgr2 = ConfigManager(config_path=cfg_path)
        assert mgr2.get('debug') is True
        assert mgr2.get('double_click_timeout') == 0.7

    def test_existing_config_is_migrated_with_missing_defaults(self, tmp_path):
        cfg_path = tmp_path / "cfg.toml"
        cfg_path.write_text(
            """
            debug = true
            auto_switch = true
            user_dict_enabled = true
            user_dict_min_weight = 2
            """,
            encoding="utf-8",
        )

        mgr = ConfigManager(config_path=str(cfg_path))

        assert mgr.get("debug") is True
        assert mgr.get("user_dict_auto_confirm") is False
        saved = cfg_path.read_text(encoding="utf-8")
        assert "user_dict_auto_confirm = false" in saved
        assert "auto_switch = true" in saved

    def test_saved_config_documents_every_setting(self, tmp_path):
        cfg_path = str(tmp_path / "cfg.toml")
        mgr = ConfigManager(config_path=cfg_path)

        assert mgr.save() is True

        lines = (tmp_path / "cfg.toml").read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("["):
                continue

            assert "=" in stripped
            assert index > 0
            assert lines[index - 1].strip().startswith("#"), stripped

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

    def test_prepare_update_validates_without_mutating(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        candidate = mgr.get_all()
        candidate["debug"] = True
        candidate["timing"]["key_press_delay"] = 0.004

        change_set = mgr.prepare_update(candidate, source="test")

        assert change_set.source == "test"
        assert change_set.old.get("debug") is False
        assert change_set.new.get("debug") is True
        assert change_set.changed_paths == frozenset({
            "debug",
            "timing.key_press_delay",
        })
        assert mgr.get("debug") is False

    def test_commit_update_writes_and_swaps_snapshot(self, tmp_path):
        cfg_path = tmp_path / "cfg.toml"
        mgr = ConfigManager(config_path=str(cfg_path))
        candidate = mgr.get_all()
        candidate["debug"] = True

        change_set = mgr.prepare_update(candidate, source="test")
        mgr.commit_update(change_set)

        assert mgr.get("debug") is True
        assert "debug = true" in cfg_path.read_text(encoding="utf-8")

    def test_commit_update_rejects_stale_snapshot(self, tmp_path):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        candidate = mgr.get_all()
        candidate["debug"] = True
        change_set = mgr.prepare_update(candidate)
        mgr.set("auto_switch", True)

        with pytest.raises(ConfigConflictError):
            mgr.commit_update(change_set)

        assert mgr.get("debug") is False
        assert mgr.get("auto_switch") is True

    def test_commit_update_save_failure_keeps_memory(self, tmp_path, monkeypatch):
        mgr = ConfigManager(config_path=str(tmp_path / "cfg.toml"))
        candidate = mgr.get_all()
        candidate["debug"] = True
        change_set = mgr.prepare_update(candidate)

        def fail_save(path, config):
            raise OSError("disk full")

        monkeypatch.setattr("lswitch.config._save_toml", fail_save)

        with pytest.raises(OSError, match="disk full"):
            mgr.commit_update(change_set)

        assert mgr.get("debug") is False

    def test_replace_can_commit_memory_only(self, tmp_path):
        cfg_path = tmp_path / "cfg.toml"
        mgr = ConfigManager(config_path=str(cfg_path))
        candidate = mgr.get_all()
        candidate["debug"] = True

        change_set = mgr.replace(candidate, source="sighup", persist=False)

        assert change_set.changed_paths == frozenset({"debug"})
        assert mgr.get("debug") is True
        assert not cfg_path.exists()

    def test_legacy_config_json_path_is_normalized_to_toml(self, tmp_path):
        legacy_path = tmp_path / "config.json"
        mgr = ConfigManager(config_path=str(legacy_path))
        mgr.set("auto_switch", True)

        assert mgr.config_path == str(tmp_path / "config.toml")
        assert mgr.save() is True
        assert not legacy_path.exists()
        assert (tmp_path / "config.toml").exists()

        loaded = load_config(config_path=str(legacy_path))
        assert loaded["auto_switch"] is True


def test_config_snapshot_does_not_expose_nested_values():
    snapshot = ConfigSnapshot({"section": {"value": 1}})

    values = snapshot.to_dict()
    values["section"]["value"] = 2

    assert snapshot.get("section") == {"value": 1}


def test_diff_config_paths_reports_changed_leaves():
    old = {
        "enabled": False,
        "timing": {"first": 0.1, "second": 0.2},
        "removed": {"leaf": 1},
    }
    new = {
        "enabled": True,
        "timing": {"first": 0.1, "second": 0.3},
        "added": {"leaf": 2},
    }

    assert diff_config_paths(old, new) == frozenset({
        "enabled",
        "timing.second",
        "removed.leaf",
        "added.leaf",
    })
