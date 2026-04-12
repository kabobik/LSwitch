"""ISelectionAdapter interface, SelectionInfo dataclass and X11SelectionAdapter."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

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

    def __init__(self, system: ISystemAdapter, debug: bool = False) -> None:
        self._system = system
        self._debug = debug

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
            time.sleep(0.02)
            self._system.xdotool_key("ctrl+v")
            time.sleep(0.05)
            # Restore the original clipboard
            if old_clip is not None:
                self._system.set_clipboard(old_clip, selection="clipboard")
            return True
        except Exception:
            return False

    def expand_selection_to_word(self) -> SelectionInfo:
        """Expand the current selection to the surrounding word via Ctrl+Shift+Left."""
        try:
            self._system.xdotool_key("ctrl+shift+Left")
            time.sleep(0.05)
        except Exception:
            pass
        return self.get_selection()
