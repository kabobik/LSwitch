"""Runtime configuration and mutable service sync helpers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from lswitch.config import ConfigChangeSet, ConfigManager
from lswitch.core.events import Event, EventType


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeConfigSnapshot:
    timing: dict
    x11_selection_timing: dict
    wayland_timing: dict
    wayland_selection_timing: dict


@dataclass(frozen=True)
class AppliedRuntimeConfig:
    timing: RuntimeConfigSnapshot
    user_dict: object | None


@dataclass(frozen=True)
class ConfigApplyResult:
    """Outcome returned to GUI, tray actions, and SIGHUP reload."""

    ok: bool
    changed_paths: frozenset[str] = frozenset()
    error: str | None = None


class RuntimeConfigController:
    """Validate, persist, apply, roll back, and notify config transitions."""

    def __init__(
        self,
        *,
        config: ConfigManager,
        apply_runtime: Callable[[ConfigChangeSet], None] | None = None,
        prepare_runtime: Callable[[ConfigChangeSet], object] | None = None,
        event_bus=None,
        log=None,
    ) -> None:
        self.config = config
        self._apply_runtime = apply_runtime or (lambda change_set: None)
        self._prepare_runtime = prepare_runtime or (lambda change_set: change_set)
        self.event_bus = event_bus
        self.log = log or logger

    def apply(
        self,
        candidate: dict,
        *,
        source: str = "unknown",
        persist: bool = True,
    ) -> ConfigApplyResult:
        """Apply a complete candidate and restore the old state on failure."""
        try:
            change_set = self.config.prepare_update(candidate, source=source)
        except Exception as exc:
            return ConfigApplyResult(ok=False, error=str(exc))

        if not change_set.changed_paths:
            return ConfigApplyResult(ok=True)

        try:
            prepared = self._prepare_runtime(change_set)
        except Exception as exc:
            return ConfigApplyResult(
                ok=False,
                changed_paths=change_set.changed_paths,
                error=str(exc),
            )

        committed = False
        try:
            self.config.commit_update(change_set, persist=persist)
            committed = True
            self._apply_runtime(prepared)
        except Exception as exc:
            if committed:
                self._rollback(change_set, persist=persist)
            return ConfigApplyResult(
                ok=False,
                changed_paths=change_set.changed_paths,
                error=str(exc),
            )

        self._publish_success(change_set)
        return ConfigApplyResult(
            ok=True,
            changed_paths=change_set.changed_paths,
        )

    def _rollback(self, change_set: ConfigChangeSet, *, persist: bool) -> None:
        reverse = ConfigChangeSet(
            old=change_set.new,
            new=change_set.old,
            changed_paths=change_set.changed_paths,
            source="rollback",
        )
        try:
            prepared = self._prepare_runtime(reverse)
            self.config.commit_update(reverse, persist=persist)
            self._apply_runtime(prepared)
        except Exception:
            self.log.exception("Runtime config rollback failed")

    def _publish_success(self, change_set: ConfigChangeSet) -> None:
        if self.event_bus is None:
            return
        data = {
            "changed_paths": change_set.changed_paths,
            "source": change_set.source,
        }
        new_values = change_set.new.to_dict()
        for path in change_set.changed_paths:
            if "." not in path and path in new_values:
                data[path] = new_values[path]
        self.event_bus.publish(
            Event(
                type=EventType.CONFIG_CHANGED,
                data=data,
                timestamp=time.time(),
            )
        )


def sync_user_dictionary_components(
    *,
    user_dict,
    user_dict_min_weight,
    auto_detector,
    conversion_engine,
    learning_service,
    debug: bool,
    manual_weight_step: int,
) -> None:
    """Propagate user dictionary settings into mutable runtime components."""
    try:
        min_weight = int(user_dict_min_weight)
    except (TypeError, ValueError):
        min_weight = 2

    if auto_detector is not None:
        auto_detector.user_dict = user_dict
        auto_detector.user_dict_min_weight = min_weight
    if conversion_engine is not None:
        conversion_engine.user_dict = user_dict
    if learning_service is not None:
        learning_service.user_dict = user_dict
        learning_service.debug = debug
        learning_service.manual_weight_step = manual_weight_step


def synced_learning_service(
    *,
    user_dict,
    user_dict_min_weight,
    learning_service,
    debug: bool,
    manual_weight_step: int,
):
    """Sync and return the learning service for short-lived use case wiring."""
    sync_user_dictionary_components(
        user_dict=user_dict,
        user_dict_min_weight=user_dict_min_weight,
        auto_detector=None,
        conversion_engine=None,
        learning_service=learning_service,
        debug=debug,
        manual_weight_step=manual_weight_step,
    )
    return learning_service


def read_runtime_config_snapshot(*, config) -> RuntimeConfigSnapshot:
    """Read runtime timing-related config tables without mutating services."""
    return RuntimeConfigSnapshot(
        timing=config.get("timing", {}),
        x11_selection_timing=config.get("x11_selection_timing", {}),
        wayland_timing=config.get("wayland_timing", {}),
        wayland_selection_timing=config.get("wayland_selection_timing", {}),
    )


def apply_runtime_timing_config(
    *,
    config,
    state_manager,
    conversion_engine,
) -> RuntimeConfigSnapshot:
    """Apply runtime timing config and return the current timing tables."""
    snapshot = read_runtime_config_snapshot(config=config)

    state_manager.double_click_timeout = config.get(
        "double_click_timeout",
        state_manager.double_click_timeout,
    )
    if conversion_engine is not None:
        conversion_engine.timing = snapshot.timing

    return snapshot


def apply_user_dictionary_config(
    *,
    config,
    user_dict,
    enable_user_dictionary,
    log,
):
    """Apply runtime user dictionary enable/disable config."""
    if config.get("user_dict_enabled"):
        try:
            return enable_user_dictionary()
        except Exception as exc:
            log.error("User dictionary initialization failed: %s", exc)
            return None

    if user_dict is not None:
        log.info("User dictionary disabled")
    return None


def enable_user_dictionary_if_needed(*, user_dict, log):
    """Return existing or newly-created runtime user dictionary."""
    if user_dict is not None:
        return user_dict

    from lswitch.intelligence.user_dictionary import UserDictionary

    user_dict = UserDictionary()
    log.info("User dictionary enabled: %s", user_dict.path)
    return user_dict


def apply_runtime_config_update(
    *,
    config,
    state_manager,
    conversion_engine,
    user_dict,
    enable_user_dictionary,
    auto_detector,
    learning_service,
    debug: bool,
    manual_weight_step: int,
    log,
) -> AppliedRuntimeConfig:
    """Apply runtime config changes and sync mutable services."""
    timing = apply_runtime_timing_config(
        config=config,
        state_manager=state_manager,
        conversion_engine=conversion_engine,
    )
    user_dict = apply_user_dictionary_config(
        config=config,
        user_dict=user_dict,
        enable_user_dictionary=enable_user_dictionary,
        log=log,
    )
    sync_user_dictionary_components(
        user_dict=user_dict,
        user_dict_min_weight=config.get("user_dict_min_weight", 2),
        auto_detector=auto_detector,
        conversion_engine=conversion_engine,
        learning_service=learning_service,
        debug=debug,
        manual_weight_step=manual_weight_step,
    )
    return AppliedRuntimeConfig(
        timing=timing,
        user_dict=user_dict,
    )
