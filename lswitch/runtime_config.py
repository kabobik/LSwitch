"""Runtime configuration and mutable service sync helpers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from lswitch.config import ConfigChangeSet, ConfigManager
from lswitch.core.events import Event, EventType
from lswitch.log import TRACE


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
    debug: bool = False
    selection_strategy_changed: bool = False


@dataclass(frozen=True)
class ConfigApplyResult:
    """Outcome returned to GUI, tray actions, and SIGHUP reload."""

    ok: bool
    changed_paths: frozenset[str] = frozenset()
    error: str | None = None


class RuntimeLoggingController:
    """Apply the effective process log level while preserving TRACE override."""

    def __init__(self, *, trace_override: bool = False, root_logger=None) -> None:
        self.trace_override = bool(trace_override)
        self.root_logger = root_logger or logging.getLogger()
        self.effective_debug = False

    def reconfigure(self, debug: bool) -> bool:
        if self.trace_override:
            level = TRACE
            self.effective_debug = True
        else:
            self.effective_debug = bool(debug)
            level = logging.DEBUG if self.effective_debug else logging.INFO
        self.root_logger.setLevel(level)
        return self.effective_debug


class RuntimeConfigController:
    """Validate, persist, apply, roll back, and notify config transitions."""

    def __init__(
        self,
        *,
        config: ConfigManager,
        apply_runtime: Callable[[object], None] | None = None,
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


def _call_capability(component, name: str, *args, **kwargs):
    if component is None:
        return None
    method = getattr(type(component), name, None)
    if not callable(method):
        return None
    return method(component, *args, **kwargs)


def set_component_debug(component, enabled: bool) -> None:
    """Update a long-lived component without imposing a shared base class."""
    if component is None:
        return
    if callable(getattr(type(component), "set_debug", None)):
        component.set_debug(enabled)
        return
    values = getattr(component, "__dict__", {})
    if "debug" in values:
        component.debug = bool(enabled)
    if "_debug" in values:
        component._debug = bool(enabled)


def apply_platform_runtime_config(
    *,
    config,
    snapshot: RuntimeConfigSnapshot,
    virtual_kb=None,
    selection=None,
    system=None,
    xkb=None,
    selection_poller=None,
    selection_tracker=None,
    event_manager=None,
    device_manager=None,
    debug: bool,
) -> bool:
    """Reconfigure existing platform objects and preserve their identities."""
    _call_capability(virtual_kb, "reconfigure_timing", snapshot.timing)
    _call_capability(system, "reconfigure_timing", snapshot.wayland_timing)

    strategy_changed = False
    if callable(getattr(type(selection), "reconfigure", None)):
        strategy_changed = bool(
            selection.reconfigure(
                strategy=config.get("wayland_selection_strategy", "auto"),
                timing=snapshot.wayland_selection_timing,
                debug=debug,
            )
        )
    else:
        _call_capability(
            selection,
            "reconfigure_timing",
            snapshot.x11_selection_timing,
        )

    if selection_poller is not None:
        _call_capability(
            selection_poller,
            "set_poll_interval",
            snapshot.x11_selection_timing.get("poll_interval", 0.5),
        )

    for component in (
        virtual_kb,
        selection,
        system,
        xkb,
        event_manager,
        device_manager,
    ):
        set_component_debug(component, debug)

    if strategy_changed and selection_tracker is not None:
        selection_tracker.reset_strategy_state()
    return strategy_changed


def apply_user_dictionary_config(
    *,
    config,
    user_dict,
    enable_user_dictionary,
    log,
):
    """Apply runtime user dictionary enable/disable config."""
    if config.get("user_dict_enabled"):
        return enable_user_dictionary()

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
    virtual_kb=None,
    selection=None,
    system=None,
    xkb=None,
    selection_poller=None,
    selection_tracker=None,
    event_manager=None,
    device_manager=None,
    layout_switch_controller=None,
) -> AppliedRuntimeConfig:
    """Apply runtime config changes and sync mutable services."""
    timing = apply_runtime_timing_config(
        config=config,
        state_manager=state_manager,
        conversion_engine=conversion_engine,
    )
    state_manager.debug = bool(debug)
    if conversion_engine is not None:
        conversion_engine.debug = bool(debug)
    if layout_switch_controller is not None:
        layout_switch_controller.reconfigure(
            keep_target_after_conversion=config.get(
                "switch_layout_after_convert",
                True,
            ),
            fallback_shortcut=config.get(
                "layout_switch_key",
                "Alt+Shift",
            ),
        )
    strategy_changed = apply_platform_runtime_config(
        config=config,
        snapshot=timing,
        virtual_kb=virtual_kb,
        selection=selection,
        system=system,
        xkb=xkb,
        selection_poller=selection_poller,
        selection_tracker=selection_tracker,
        event_manager=event_manager,
        device_manager=device_manager,
        debug=debug,
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
        debug=debug,
        selection_strategy_changed=strategy_changed,
    )
