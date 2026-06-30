"""ISelectionAdapter interface, SelectionInfo dataclass and X11SelectionAdapter."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from lswitch.intelligence.maps import EN_TO_RU
from lswitch.platform.system_adapter import ISystemAdapter


@dataclass
class SelectionInfo:
    text: str
    owner_id: int       # XGetSelectionOwner window ID
    timestamp: float    # Time of retrieval


class ISelectionAdapter(ABC):
    @abstractmethod
    def get_selection(self) -> SelectionInfo: ...

    @abstractmethod
    def has_fresh_selection(self) -> bool: ...

    @abstractmethod
    def replace_selection(self, new_text: str) -> bool: ...

    @abstractmethod
    def expand_selection_to_word(self) -> SelectionInfo: ...


def get_passive_selection_reader(selection) -> Callable[[], SelectionInfo] | None:
    """Return a no-shortcut selection reader when an adapter provides one."""
    if selection is None:
        return None
    if getattr(type(selection), "get_passive_selection", None) is None:
        return None
    reader = getattr(selection, "get_passive_selection", None)
    return reader if callable(reader) else None


LAYOUT_WORD_CONTINUATION_CHARS = frozenset(
    ch for ch, mapped in EN_TO_RU.items()
    if not ch.isalpha() and mapped.isalpha()
)


def _leading_added_text(previous: str, current: str) -> str:
    if not previous or not current or current == previous:
        return ""
    if current.endswith(previous):
        return current[: -len(previous)]
    return ""


def _is_layout_word_char(ch: str) -> bool:
    return bool(ch and (ch.isalpha() or ch in LAYOUT_WORD_CONTINUATION_CHARS))


# ---------------------------------------------------------------------------
# X11SelectionAdapter — concrete implementation
# ---------------------------------------------------------------------------

def _get_selection_owner_id() -> int:
    """Return window ID of the PRIMARY selection owner via Xlib, or 0."""
    try:
        from Xlib import display as xdisplay, Xatom, X
        d = xdisplay.Display()
        owner = d.get_selection_owner(Xatom.PRIMARY)
        owner_id = owner.id if owner and owner != X.NONE else 0
        d.close()
        return owner_id
    except Exception:
        return 0


class X11SelectionAdapter(ISelectionAdapter):
    """Selection adapter for X11 — reads PRIMARY selection and tracks freshness.

    Freshness is determined by **(owner_id, text)** pair: even if the user
    re-selects the same text, a new owner_id marks the selection as fresh.
    """

    PASTE_DELAY = 0.02
    RESTORE_DELAY = 0.05
    EXPAND_SELECTION_DELAY = 0.05
    MAX_LAYOUT_WORD_PROBE_CHARS = 64

    def __init__(
        self,
        system: ISystemAdapter,
        debug: bool = False,
        timing: dict | None = None,
    ) -> None:
        self._system = system
        self._debug = debug
        timing = timing or {}
        self.PASTE_DELAY = float(timing.get("paste_delay", type(self).PASTE_DELAY))
        self.RESTORE_DELAY = float(
            timing.get("restore_delay", type(self).RESTORE_DELAY)
        )
        self.EXPAND_SELECTION_DELAY = float(
            timing.get(
                "expand_selection_delay",
                type(self).EXPAND_SELECTION_DELAY,
            )
        )

        # Cached previous state for freshness comparison
        self._prev_owner_id: int = 0
        self._prev_text: str = ""

    # -- ISelectionAdapter --------------------------------------------------

    def get_selection(self) -> SelectionInfo:
        text = self._system.get_clipboard(selection="primary")
        owner_id = _get_selection_owner_id()
        return SelectionInfo(text=text, owner_id=owner_id, timestamp=time.time())

    def has_fresh_selection(self) -> bool:
        """Determine whether there is a *fresh* selection.

        A selection is considered fresh when **any** of the following changed
        compared to the last call:
        - ``owner_id`` (different window grabbed PRIMARY)
        - ``text`` (different content selected)

        Even if the text is identical, a different ``owner_id`` means the user
        made a new selection and the result should be treated as fresh (v1 bug fix).
        """
        info = self.get_selection()
        if not info.text:
            return False

        owner_changed = info.owner_id != self._prev_owner_id and info.owner_id != 0
        text_changed = info.text != self._prev_text

        is_fresh = owner_changed or text_changed

        if is_fresh:
            self._prev_owner_id = info.owner_id
            self._prev_text = info.text

        return is_fresh

    def replace_selection(self, new_text: str) -> bool:
        """Replace the current selection by setting clipboard and pasting.

        Sequence: save clipboard → set clipboard → Ctrl+V → restore clipboard.
        """
        try:
            old_clip = self._system.get_clipboard(selection="clipboard")
            self._system.set_clipboard(new_text, selection="clipboard")
            time.sleep(self.PASTE_DELAY)
            self._system.send_key_sequence("ctrl+v")
            time.sleep(self.RESTORE_DELAY)
            # Restore the original clipboard
            if old_clip is not None:
                self._system.set_clipboard(old_clip, selection="clipboard")
            return True
        except Exception:
            return False

    def expand_selection_to_word(self) -> SelectionInfo:
        """Expand the current selection to the surrounding word via Ctrl+Shift+Left."""
        try:
            self._system.send_key_sequence("ctrl+shift+Left")
            time.sleep(self.EXPAND_SELECTION_DELAY)
        except Exception:
            pass
        return self._expand_through_layout_word_boundaries(self.get_selection())

    def _expand_through_layout_word_boundaries(
        self,
        initial: SelectionInfo,
    ) -> SelectionInfo:
        if not initial.text:
            return initial

        previous = initial
        probing = False
        for _ in range(self.MAX_LAYOUT_WORD_PROBE_CHARS):
            try:
                self._system.send_key_sequence("shift+Left")
                time.sleep(self.EXPAND_SELECTION_DELAY)
                current = self.get_selection()
            except Exception:
                return previous

            added = _leading_added_text(previous.text, current.text)
            if not added:
                return previous

            added_char = added[-1]
            if not probing:
                if added_char not in LAYOUT_WORD_CONTINUATION_CHARS:
                    self._shrink_selection_right()
                    return initial
                probing = True
            elif not _is_layout_word_char(added_char):
                self._shrink_selection_right()
                return previous

            previous = current

        return previous

    def _shrink_selection_right(self) -> None:
        try:
            self._system.send_key_sequence("shift+Right")
            time.sleep(self.EXPAND_SELECTION_DELAY)
        except Exception:
            pass
