"""ConversionEngine — chooses conversion mode and executes it."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lswitch.core.states import StateContext
    from lswitch.platform.xkb_adapter import IXKBAdapter
    from lswitch.platform.selection_adapter import ISelectionAdapter
    from lswitch.platform.system_adapter import ISystemAdapter
    from lswitch.input.virtual_keyboard import VirtualKeyboard
    from lswitch.intelligence.dictionary_service import DictionaryService
    from lswitch.intelligence.user_dictionary import UserDictionary

logger = logging.getLogger(__name__)


class ConversionEngine:
    """Orchestrates text conversion: retype or selection mode."""

    def __init__(
        self,
        xkb: "IXKBAdapter",
        selection: "ISelectionAdapter",
        virtual_kb: "VirtualKeyboard",
        dictionary: "DictionaryService",
        system: "ISystemAdapter",
        user_dict: "UserDictionary | None" = None,
        debug: bool = False,
    ):
        self.xkb = xkb
        self.selection = selection
        self.virtual_kb = virtual_kb
        self.dictionary = dictionary
        self.system = system
        self.user_dict = user_dict
        self.debug = debug

    def choose_mode(self, context: "StateContext") -> str:
        """Return 'selection' or 'retype' based on current state."""
        if context.backspace_hold_active:
            return "selection"
        if self.selection.has_fresh_selection():
            return "selection"
        if context.chars_in_buffer > 0:
            return "retype"
        return "selection"

    def convert(self, context: "StateContext") -> bool:
        """Perform conversion. Returns True on success."""
        from lswitch.core.modes import RetypeMode, SelectionMode

        mode = self.choose_mode(context)
        if self.debug:
            logger.debug("Converting in mode: %s", mode)
        if mode == "retype":
            retype = RetypeMode(self.virtual_kb, self.xkb, self.system, self.debug)
            return retype.execute(context)
        else:
            sel_mode = SelectionMode(self.selection, self.xkb, self.system, self.debug)
            return sel_mode.execute(context)
