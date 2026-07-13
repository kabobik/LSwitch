"""Qt-free settings draft, binding registry, and dependency rules."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable

from lswitch.config import DEFAULT_CONFIG


PAGE_GENERAL = "general"
PAGE_AUTO = "auto"
PAGE_DICTIONARIES = "dictionaries"
PAGE_SELECTION = "selection"
PAGE_ADVANCED = "advanced"
SETTINGS_PAGES = (
    PAGE_GENERAL,
    PAGE_AUTO,
    PAGE_DICTIONARIES,
    PAGE_SELECTION,
    PAGE_ADVANCED,
)


@dataclass(frozen=True)
class SettingsBinding:
    path: str
    page: str
    widget: str
    label_key: str
    help_key: str
    minimum: float | int | None = None
    maximum: float | int | None = None
    decimals: int | None = None
    options: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()


def _binding(
    path: str,
    page: str,
    widget: str,
    *,
    minimum=None,
    maximum=None,
    decimals=None,
    options=(),
    platforms=(),
) -> SettingsBinding:
    return SettingsBinding(
        path=path,
        page=page,
        widget=widget,
        label_key=f"settings_{path.replace('.', '_')}",
        help_key=f"settings_{path.replace('.', '_')}_help",
        minimum=minimum,
        maximum=maximum,
        decimals=decimals,
        options=tuple(options),
        platforms=tuple(platforms),
    )


SETTINGS_BINDINGS: tuple[SettingsBinding, ...] = (
    _binding("double_click_timeout", PAGE_GENERAL, "float", minimum=0.05, maximum=10.0, decimals=6),
    _binding("switch_layout_after_convert", PAGE_GENERAL, "bool"),
    _binding("layout_switch_key", PAGE_GENERAL, "shortcut"),
    _binding("auto_switch", PAGE_AUTO, "bool"),
    _binding("auto_switch_threshold", PAGE_AUTO, "int", minimum=0, maximum=2_147_483_647),
    _binding("auto_switch_mid_word", PAGE_AUTO, "bool"),
    _binding("mid_word_min_prefix_len", PAGE_AUTO, "int", minimum=1, maximum=32),
    _binding("system_dict_enabled", PAGE_DICTIONARIES, "bool"),
    _binding("system_dict_en_path", PAGE_DICTIONARIES, "path"),
    _binding("system_dict_ru_path", PAGE_DICTIONARIES, "path"),
    _binding("user_dict_enabled", PAGE_DICTIONARIES, "bool"),
    _binding("user_dict_auto_confirm", PAGE_DICTIONARIES, "bool"),
    _binding("user_dict_min_weight", PAGE_DICTIONARIES, "int", minimum=0, maximum=2_147_483_647),
    _binding(
        "wayland_selection_strategy",
        PAGE_SELECTION,
        "choice",
        options=("auto", "clipboard_copy", "primary_selection", "disabled"),
        platforms=("wayland",),
    ),
    _binding("x11_selection_timing.poll_interval", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("x11",)),
    _binding("x11_selection_timing.paste_delay", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("x11",)),
    _binding("x11_selection_timing.restore_delay", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("x11",)),
    _binding("x11_selection_timing.expand_selection_delay", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("x11",)),
    _binding("wayland_timing.wl_clipboard_timeout", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("wayland",)),
    _binding("wayland_selection_timing.copy_wait_timeout", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("wayland",)),
    _binding("wayland_selection_timing.copy_poll_interval", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("wayland",)),
    _binding("wayland_selection_timing.copy_retry_delay", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("wayland",)),
    _binding("wayland_selection_timing.paste_delay", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("wayland",)),
    _binding("wayland_selection_timing.restore_delay", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("wayland",)),
    _binding("wayland_selection_timing.expand_selection_delay", PAGE_SELECTION, "float", minimum=0.0, maximum=30.0, decimals=6, platforms=("wayland",)),
    _binding("debug", PAGE_ADVANCED, "bool"),
    _binding("timing.key_press_delay", PAGE_ADVANCED, "float", minimum=0.0, maximum=30.0, decimals=6),
    _binding("timing.key_repeat_delay", PAGE_ADVANCED, "float", minimum=0.0, maximum=30.0, decimals=6),
    _binding("timing.retype_before_replay_delay", PAGE_ADVANCED, "float", minimum=0.0, maximum=30.0, decimals=6),
    _binding("timing.direct_type_after_layout_switch_delay", PAGE_ADVANCED, "float", minimum=0.0, maximum=30.0, decimals=6),
    _binding("timing.undo_before_replay_delay", PAGE_ADVANCED, "float", minimum=0.0, maximum=30.0, decimals=6),
    _binding("timing.auto_before_replay_delay", PAGE_ADVANCED, "float", minimum=0.0, maximum=30.0, decimals=6),
    _binding("timing.auto_before_space_delay", PAGE_ADVANCED, "float", minimum=0.0, maximum=30.0, decimals=6),
)
SETTINGS_BINDING_BY_PATH = {
    binding.path: binding for binding in SETTINGS_BINDINGS
}


def platform_visibility(session_type: str | None) -> dict[str, bool]:
    """Return visible settings for x11/wayland; unknown keeps all visible."""
    normalized = (
        session_type.strip().lower()
        if isinstance(session_type, str)
        else "unknown"
    )
    if normalized not in {"x11", "wayland"}:
        normalized = "unknown"
    return {
        binding.path: (
            not binding.platforms
            or normalized == "unknown"
            or normalized in binding.platforms
        )
        for binding in SETTINGS_BINDINGS
    }


def dotted_get(values: dict, path: str, default=None):
    current: Any = values
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return copy.deepcopy(default)
        current = current[part]
    return copy.deepcopy(current)


def dotted_set(values: dict, path: str, value) -> None:
    parts = path.split(".")
    current = values
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = copy.deepcopy(value)


def merge_dirty_paths(latest: dict, draft: dict, dirty_paths: Iterable[str]) -> dict:
    merged = copy.deepcopy(latest)
    for path in dirty_paths:
        dotted_set(merged, path, dotted_get(draft, path))
    return merged


def dependency_enabled(values: dict) -> dict[str, bool]:
    """Return enabled state for every setting path in the current draft."""
    enabled = {binding.path: True for binding in SETTINGS_BINDINGS}
    auto_switch = bool(dotted_get(values, "auto_switch", False))
    mid_word = bool(dotted_get(values, "auto_switch_mid_word", False))
    system_dict = bool(dotted_get(values, "system_dict_enabled", False))
    user_dict = bool(dotted_get(values, "user_dict_enabled", False))
    strategy = dotted_get(values, "wayland_selection_strategy", "auto")

    enabled["auto_switch_threshold"] = auto_switch
    enabled["mid_word_min_prefix_len"] = mid_word
    enabled["system_dict_enabled"] = mid_word
    enabled["system_dict_en_path"] = mid_word and system_dict
    enabled["system_dict_ru_path"] = mid_word and system_dict
    enabled["user_dict_min_weight"] = user_dict
    enabled["user_dict_auto_confirm"] = user_dict and auto_switch

    wayland_paths = [
        binding.path
        for binding in SETTINGS_BINDINGS
        if binding.path.startswith("wayland_selection_timing.")
    ]
    if strategy == "disabled":
        for path in wayland_paths:
            enabled[path] = False
    elif strategy == "primary_selection":
        for child in (
            "copy_wait_timeout",
            "copy_poll_interval",
            "copy_retry_delay",
            "paste_delay",
            "restore_delay",
        ):
            enabled[f"wayland_selection_timing.{child}"] = False
    return enabled


class SettingsDraftModel:
    """Own a mergeable settings draft without mutating committed config."""

    def __init__(self, committed: dict | None = None) -> None:
        self._committed: dict = {}
        self._draft: dict = {}
        self.dirty_paths: set[str] = set()
        self.external_change_pending = False
        self.load(committed or DEFAULT_CONFIG)

    @property
    def is_dirty(self) -> bool:
        return bool(self.dirty_paths)

    def committed_values(self) -> dict:
        return copy.deepcopy(self._committed)

    def draft_values(self) -> dict:
        return copy.deepcopy(self._draft)

    def load(self, committed: dict) -> None:
        self._committed = copy.deepcopy(committed)
        self._draft = copy.deepcopy(committed)
        self.dirty_paths.clear()
        self.external_change_pending = False

    def get(self, path: str, default=None):
        return dotted_get(self._draft, path, default)

    def set(self, path: str, value) -> None:
        if path not in SETTINGS_BINDING_BY_PATH:
            raise KeyError(f"Unknown settings path: {path}")
        dotted_set(self._draft, path, value)
        if self.get(path) == dotted_get(self._committed, path):
            self.dirty_paths.discard(path)
        else:
            self.dirty_paths.add(path)

    def reset_page(self, page: str) -> None:
        if page not in SETTINGS_PAGES:
            raise KeyError(f"Unknown settings page: {page}")
        for binding in SETTINGS_BINDINGS:
            if binding.page == page:
                self.set(binding.path, dotted_get(DEFAULT_CONFIG, binding.path))

    def reset_all(self) -> None:
        for binding in SETTINGS_BINDINGS:
            self.set(binding.path, dotted_get(DEFAULT_CONFIG, binding.path))

    def build_candidate(self, latest_committed: dict | None = None) -> dict:
        latest = latest_committed or self._committed
        return merge_dirty_paths(latest, self._draft, self.dirty_paths)

    def handle_external_change(self, latest_committed: dict) -> bool:
        """Refresh a clean draft or rebase dirty values on the latest snapshot."""
        if not self.is_dirty:
            self.load(latest_committed)
            return True

        edited = {
            path: self.get(path)
            for path in self.dirty_paths
        }
        self._committed = copy.deepcopy(latest_committed)
        self._draft = copy.deepcopy(latest_committed)
        self.dirty_paths.clear()
        for path, value in edited.items():
            self.set(path, value)
        self.external_change_pending = True
        return False

    def mark_committed(self, committed: dict) -> None:
        self.load(committed)

    def enabled_paths(self) -> dict[str, bool]:
        return dependency_enabled(self._draft)
