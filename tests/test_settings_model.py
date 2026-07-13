"""Tests for the Qt-free settings draft and dependency matrix."""

from __future__ import annotations

import copy

import pytest

from lswitch.config import DEFAULT_CONFIG
from lswitch.ui.settings_model import (
    PAGE_AUTO,
    SETTINGS_BINDINGS,
    SettingsDraftModel,
    dependency_enabled,
    dotted_get,
    dotted_set,
    merge_dirty_paths,
    platform_visibility,
)


def _leaf_paths(values: dict, prefix: str = "") -> set[str]:
    paths = set()
    for key, value in values.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            paths.update(_leaf_paths(value, path))
        else:
            paths.add(path)
    return paths


def test_binding_registry_covers_all_31_config_paths_once():
    paths = [binding.path for binding in SETTINGS_BINDINGS]

    assert len(paths) == 31
    assert len(set(paths)) == 31
    assert set(paths) == _leaf_paths(DEFAULT_CONFIG)


def test_nested_draft_is_isolated_and_tracks_exact_dirty_path():
    committed = copy.deepcopy(DEFAULT_CONFIG)
    model = SettingsDraftModel(committed)

    model.set("timing.key_press_delay", 0.123456)

    assert committed["timing"]["key_press_delay"] != 0.123456
    assert model.dirty_paths == {"timing.key_press_delay"}
    draft = model.draft_values()
    draft["timing"]["key_press_delay"] = 9.0
    assert model.get("timing.key_press_delay") == 0.123456


def test_setting_original_value_again_clears_dirty_path():
    model = SettingsDraftModel(DEFAULT_CONFIG)
    original = model.get("auto_switch_threshold")

    model.set("auto_switch_threshold", original + 10)
    model.set("auto_switch_threshold", original)

    assert model.is_dirty is False


def test_dirty_merge_preserves_newer_external_values():
    model = SettingsDraftModel(DEFAULT_CONFIG)
    model.set("auto_switch_threshold", 17)
    latest = copy.deepcopy(DEFAULT_CONFIG)
    latest["user_dict_enabled"] = True

    candidate = model.build_candidate(latest)

    assert candidate["auto_switch_threshold"] == 17
    assert candidate["user_dict_enabled"] is True


def test_external_change_refreshes_clean_draft():
    model = SettingsDraftModel(DEFAULT_CONFIG)
    latest = copy.deepcopy(DEFAULT_CONFIG)
    latest["auto_switch"] = True

    refreshed = model.handle_external_change(latest)

    assert refreshed is True
    assert model.get("auto_switch") is True
    assert model.is_dirty is False


def test_external_change_rebases_but_does_not_overwrite_dirty_draft():
    model = SettingsDraftModel(DEFAULT_CONFIG)
    model.set("auto_switch_threshold", 23)
    latest = copy.deepcopy(DEFAULT_CONFIG)
    latest["user_dict_enabled"] = True

    refreshed = model.handle_external_change(latest)

    assert refreshed is False
    assert model.get("auto_switch_threshold") == 23
    assert model.get("user_dict_enabled") is True
    assert model.dirty_paths == {"auto_switch_threshold"}
    assert model.external_change_pending is True


def test_reset_page_only_changes_paths_on_current_page():
    committed = copy.deepcopy(DEFAULT_CONFIG)
    committed["auto_switch"] = True
    committed["auto_switch_threshold"] = 99
    committed["debug"] = True
    model = SettingsDraftModel(committed)

    model.reset_page(PAGE_AUTO)

    assert model.get("auto_switch") == DEFAULT_CONFIG["auto_switch"]
    assert model.get("auto_switch_threshold") == DEFAULT_CONFIG["auto_switch_threshold"]
    assert model.get("debug") is True
    assert "debug" not in model.dirty_paths


def test_reset_all_uses_owned_defaults_without_committing():
    committed = copy.deepcopy(DEFAULT_CONFIG)
    committed["debug"] = True
    committed["timing"]["key_press_delay"] = 1.0
    model = SettingsDraftModel(committed)

    model.reset_all()

    assert model.get("debug") is False
    assert model.get("timing.key_press_delay") == DEFAULT_CONFIG["timing"]["key_press_delay"]
    assert committed["debug"] is True


@pytest.mark.parametrize(
    ("updates", "path", "expected"),
    [
        ({"auto_switch": False}, "auto_switch_threshold", False),
        ({"auto_switch": True}, "auto_switch_threshold", True),
        ({"auto_switch": False}, "mid_word_min_prefix_len", False),
        ({"auto_switch": False}, "system_dict_enabled", False),
        (
            {"auto_switch": True, "system_dict_enabled": False},
            "system_dict_en_path",
            False,
        ),
        (
            {"auto_switch": True, "system_dict_enabled": True},
            "system_dict_ru_path",
            True,
        ),
        ({"user_dict_enabled": False}, "user_dict_min_weight", False),
        (
            {"wayland_selection_strategy": "disabled"},
            "wayland_selection_timing.expand_selection_delay",
            False,
        ),
        (
            {"wayland_selection_strategy": "primary_selection"},
            "wayland_selection_timing.paste_delay",
            False,
        ),
        (
            {"wayland_selection_strategy": "primary_selection"},
            "wayland_selection_timing.expand_selection_delay",
            True,
        ),
    ],
)
def test_dependency_matrix(updates, path, expected):
    values = copy.deepcopy(DEFAULT_CONFIG)
    values.update(updates)

    assert dependency_enabled(values)[path] is expected


@pytest.mark.parametrize(
    ("session_type", "visible_platform", "hidden_platform"),
    [
        ("x11", "x11", "wayland"),
        ("wayland", "wayland", "x11"),
    ],
)
def test_platform_visibility_hides_only_inactive_environment(
    session_type,
    visible_platform,
    hidden_platform,
):
    visibility = platform_visibility(session_type)

    for binding in SETTINGS_BINDINGS:
        if binding.platforms == (visible_platform,):
            assert visibility[binding.path] is True
        elif binding.platforms == (hidden_platform,):
            assert visibility[binding.path] is False
        elif not binding.platforms:
            assert visibility[binding.path] is True


@pytest.mark.parametrize("session_type", [None, "", "unknown", "other"])
def test_unknown_platform_keeps_every_setting_visible(session_type):
    assert all(platform_visibility(session_type).values())


def test_dotted_helpers_and_merge_do_not_alias_nested_values():
    values = {}
    dotted_set(values, "timing.key_press_delay", 0.5)
    latest = copy.deepcopy(DEFAULT_CONFIG)
    merged = merge_dirty_paths(latest, values, {"timing.key_press_delay"})

    assert dotted_get(values, "timing.key_press_delay") == 0.5
    assert merged["timing"]["key_press_delay"] == 0.5
    merged["timing"]["key_repeat_delay"] = 9.0
    assert latest["timing"]["key_repeat_delay"] != 9.0
