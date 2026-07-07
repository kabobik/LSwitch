"""Runtime component factories."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.event_bus import EventBus
from lswitch.core.event_manager import EventManager
from lswitch.core.input_router import InputEventRouter
from lswitch.core.learning_service import LearningService
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.state_manager import StateManager
from lswitch.core.typed_buffer import TypedBufferService
from lswitch.intelligence.auto_detector import AutoDetector
from lswitch.intelligence.dictionary_service import DictionaryService
from lswitch.intelligence.ngram_analyzer import NgramAnalyzer

logger = logging.getLogger(__name__)


class SelectionPollerThread(threading.Thread):
    """Background daemon thread polling platform selection changes."""

    def __init__(
        self,
        selection_adapter,
        on_selection_changed=None,
        poll_interval: float = 0.5,
    ):
        super().__init__(daemon=True, name="selection-poller")
        self._selection = selection_adapter
        self._running = True
        self._prev_text: str = ""
        self._prev_owner_id: int = 0
        self._on_selection_changed = on_selection_changed
        self._poll_interval = poll_interval

    def run(self):
        import time

        while self._running:
            try:
                info = self._selection.get_selection()
                text_changed = info.text != self._prev_text
                owner_changed = info.owner_id != self._prev_owner_id
                if text_changed or owner_changed:
                    self._prev_text = info.text
                    self._prev_owner_id = info.owner_id
                    logger.debug(
                        "Selection changed: text=%r owner=0x%x",
                        info.text[:80] if info.text else "",
                        info.owner_id,
                    )
                    if self._on_selection_changed:
                        self._on_selection_changed(info.text, info.owner_id)
            except Exception as exc:
                logger.trace("selection-poller error: %s", exc)  # type: ignore[attr-defined]
            time.sleep(self._poll_interval)

    def stop(self):
        self._running = False


@dataclass(frozen=True)
class RuntimeCoreComponents:
    event_bus: EventBus
    state_manager: StateManager
    typed_buffer: TypedBufferService
    selection_tracker: SelectionFreshnessTracker
    learning_service: LearningService


@dataclass(frozen=True)
class ConversionRuntimeComponents:
    dictionary: DictionaryService
    ngrams: NgramAnalyzer
    auto_detector: AutoDetector
    conversion_engine: ConversionEngine


@dataclass(frozen=True)
class InputDeviceRuntimeComponents:
    event_manager: EventManager
    device_manager: object
    udev_monitor: object


def create_core_components(
    *,
    double_click_timeout: float,
    debug: bool,
    manual_weight_step: int,
) -> RuntimeCoreComponents:
    """Create core services that do not require platform adapters."""
    return RuntimeCoreComponents(
        event_bus=EventBus(),
        state_manager=StateManager(
            double_click_timeout=double_click_timeout,
            debug=debug,
        ),
        typed_buffer=TypedBufferService(),
        selection_tracker=SelectionFreshnessTracker(),
        learning_service=LearningService(
            None,
            debug=debug,
            manual_weight_step=manual_weight_step,
        ),
    )


def create_input_router(
    *,
    core: RuntimeCoreComponents,
    decode_buffer,
    auto_conversion_enabled,
    try_auto_conversion_at_space,
    get_pending_auto_space,
    set_pending_auto_space,
    clear_last_retype_events,
    clear_last_auto_marker,
    inject_deferred_space,
    request_conversion,
    prime_selection_baseline_on_click,
    read_mouse_release_selection,
) -> InputEventRouter:
    """Create the input router around app/runtime callbacks."""
    return InputEventRouter(
        state_manager=core.state_manager,
        typed_buffer=core.typed_buffer,
        selection_tracker=core.selection_tracker,
        decode_buffer=decode_buffer,
        auto_conversion_enabled=auto_conversion_enabled,
        try_auto_conversion_at_space=try_auto_conversion_at_space,
        get_pending_auto_space=get_pending_auto_space,
        set_pending_auto_space=set_pending_auto_space,
        clear_last_retype_events=clear_last_retype_events,
        clear_last_auto_marker=clear_last_auto_marker,
        inject_deferred_space=inject_deferred_space,
        request_conversion=request_conversion,
        prime_selection_baseline_on_click=prime_selection_baseline_on_click,
        read_mouse_release_selection=read_mouse_release_selection,
    )


def create_conversion_runtime(
    *,
    xkb,
    selection,
    virtual_kb,
    system,
    user_dict,
    user_dict_min_weight: int,
    debug: bool,
    timing: dict,
) -> ConversionRuntimeComponents:
    """Create dictionary, auto-detection, and conversion executor services."""
    dictionary = DictionaryService()
    ngrams = NgramAnalyzer()
    return ConversionRuntimeComponents(
        dictionary=dictionary,
        ngrams=ngrams,
        auto_detector=AutoDetector(
            dictionary=dictionary,
            ngrams=ngrams,
            user_dict=user_dict,
            user_dict_min_weight=user_dict_min_weight,
        ),
        conversion_engine=ConversionEngine(
            xkb=xkb,
            selection=selection,
            virtual_kb=virtual_kb,
            dictionary=dictionary,
            system=system,
            user_dict=user_dict,
            debug=debug,
            timing=timing,
        ),
    )


def create_input_device_runtime(
    *,
    event_bus: EventBus,
    virtual_kb,
    debug: bool,
) -> InputDeviceRuntimeComponents:
    """Create raw input event and hot-plug runtime services."""
    from lswitch.input.device_manager import DeviceManager
    from lswitch.input.udev_monitor import UdevMonitor
    from lswitch.input.virtual_keyboard import VirtualKeyboard

    event_manager = EventManager(event_bus, debug=debug)
    device_manager = DeviceManager(debug=debug)
    if virtual_kb:
        device_manager.set_virtual_kb_name(VirtualKeyboard.DEVICE_NAME)
    udev_monitor = UdevMonitor(
        on_added=device_manager._try_add_device,
        on_removed=lambda path: device_manager.remove_device(path),
    )
    return InputDeviceRuntimeComponents(
        event_manager=event_manager,
        device_manager=device_manager,
        udev_monitor=udev_monitor,
    )


def run_evdev_event_loop(
    *,
    is_running,
    device_manager,
    event_manager,
    timeout: float = 0.1,
) -> None:
    """Run the blocking evdev polling loop until the runtime is stopped."""
    while is_running():
        for device, event in device_manager.get_events(timeout=timeout):
            event_manager.handle_raw_event(event, device.name)


def stop_runtime_resources(
    *,
    selection_poller,
    udev_monitor,
    device_manager,
    virtual_kb,
    xkb,
    pid_lock,
):
    """Stop runtime-owned resources and return the remaining PID lock state."""
    if selection_poller:
        selection_poller.stop()
    if udev_monitor:
        try:
            udev_monitor.stop()
        except Exception:
            pass
    if device_manager:
        try:
            device_manager.close()
        except Exception:
            pass
    if virtual_kb:
        try:
            virtual_kb.close()
        except Exception:
            pass
    if xkb and hasattr(xkb, "close"):
        try:
            xkb.close()
        except Exception:
            pass
    if pid_lock:
        pid_lock.release()
        return None
    return pid_lock
