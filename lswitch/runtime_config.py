"""Runtime configuration and mutable service sync helpers."""

from __future__ import annotations

from dataclasses import dataclass


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
