"""Tests for transactional runtime configuration orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.config import ConfigManager
from lswitch.core.event_bus import EventBus
from lswitch.core.events import EventType
from lswitch.runtime_config import RuntimeConfigController


def test_controller_commits_applies_and_notifies(tmp_path):
    config = ConfigManager(config_path=str(tmp_path / "config.toml"))
    event_bus = EventBus()
    applied = []
    events = []
    event_bus.subscribe(EventType.CONFIG_CHANGED, events.append)
    controller = RuntimeConfigController(
        config=config,
        apply_runtime=lambda change: applied.append(change),
        event_bus=event_bus,
    )
    candidate = config.get_all()
    candidate["auto_switch"] = True

    result = controller.apply(candidate, source="test")

    assert result.ok is True
    assert result.changed_paths == frozenset({"auto_switch"})
    assert config.get("auto_switch") is True
    assert len(applied) == 1
    assert len(events) == 1
    assert events[0].data["changed_paths"] == frozenset({"auto_switch"})
    assert events[0].data["source"] == "test"
    assert events[0].data["auto_switch"] is True


def test_controller_validation_failure_has_no_side_effects(tmp_path):
    config = ConfigManager(config_path=str(tmp_path / "config.toml"))
    apply_runtime = MagicMock()
    controller = RuntimeConfigController(
        config=config,
        apply_runtime=apply_runtime,
    )
    candidate = config.get_all()
    candidate["double_click_timeout"] = "invalid"

    result = controller.apply(candidate)

    assert result.ok is False
    assert "double_click_timeout" in result.error
    assert config.get("double_click_timeout") == 0.3
    apply_runtime.assert_not_called()


def test_controller_runtime_failure_rolls_back_memory_and_disk(tmp_path):
    path = tmp_path / "config.toml"
    config = ConfigManager(config_path=str(path))
    assert config.save() is True
    runtime_values = []

    def apply_runtime(change):
        runtime_values.append(config.get("debug"))
        if len(runtime_values) == 1:
            raise RuntimeError("runtime rejected update")

    controller = RuntimeConfigController(
        config=config,
        apply_runtime=apply_runtime,
    )
    candidate = config.get_all()
    candidate["debug"] = True

    result = controller.apply(candidate)

    assert result.ok is False
    assert result.error == "runtime rejected update"
    assert runtime_values == [True, False]
    assert config.get("debug") is False
    assert "debug = false" in path.read_text(encoding="utf-8")


def test_controller_save_failure_does_not_touch_runtime(tmp_path, monkeypatch):
    config = ConfigManager(config_path=str(tmp_path / "config.toml"))
    apply_runtime = MagicMock()
    controller = RuntimeConfigController(
        config=config,
        apply_runtime=apply_runtime,
    )
    candidate = config.get_all()
    candidate["debug"] = True
    monkeypatch.setattr(
        "lswitch.config._save_toml",
        MagicMock(side_effect=OSError("disk full")),
    )

    result = controller.apply(candidate)

    assert result.ok is False
    assert result.error == "disk full"
    assert config.get("debug") is False
    apply_runtime.assert_not_called()


def test_controller_noop_skips_runtime_file_and_event(tmp_path):
    path = tmp_path / "config.toml"
    config = ConfigManager(config_path=str(path))
    apply_runtime = MagicMock()
    event_bus = MagicMock()
    controller = RuntimeConfigController(
        config=config,
        apply_runtime=apply_runtime,
        event_bus=event_bus,
    )

    result = controller.apply(config.get_all())

    assert result.ok is True
    assert result.changed_paths == frozenset()
    assert not path.exists()
    apply_runtime.assert_not_called()
    event_bus.publish.assert_not_called()


def test_controller_memory_only_apply_supports_sighup(tmp_path):
    path = tmp_path / "config.toml"
    config = ConfigManager(config_path=str(path))
    controller = RuntimeConfigController(config=config)
    candidate = config.get_all()
    candidate["debug"] = True

    result = controller.apply(candidate, source="sighup", persist=False)

    assert result.ok is True
    assert config.get("debug") is True
    assert not path.exists()
