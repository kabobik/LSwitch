"""UserDictionary — per-user word learning with symmetric weights.

NOTE: Logic ported from archive/lswitch/user_dictionary.py.
Uses persistence.py for atomic saves instead of direct json.dump.
"""

from __future__ import annotations

import os
import time
import logging

from lswitch.intelligence.persistence import load_json, save_json

logger = logging.getLogger(__name__)

DEFAULT_PATH = os.path.expanduser("~/.config/lswitch/user_dict.json")


class UserDictionary:
    """Stores word weights: >0 = prefer EN, <0 = prefer RU."""

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self.data: dict = load_json(path, {
            "words": {},
        })
        if "words" not in self.data:
            self.data["words"] = {}

    def get_weight(self, word: str, lang: str) -> int:
        key = self._key(word, lang)
        return int(self.data["words"].get(key, 0))

    def add_correction(self, word: str, lang: str, debug: bool = False, weight_step: int = 2) -> None:
        """Penalise auto-conversion for this word (-weight_step weight)."""
        weight_step = max(1, weight_step)
        key = self._key(word, lang)
        current = self.get_weight(word, lang)
        new_weight = current - weight_step
        self.data["words"][key] = new_weight
        if debug:
            logger.debug("UserDict correction: %s weight → %d", key, new_weight)
        self.flush()

    def add_confirmation(self, word: str, lang: str, debug: bool = False, weight_step: int = 1) -> None:
        """Confirm auto-conversion was correct (+ weight_step)."""
        weight_step = max(1, weight_step)
        key = self._key(word, lang)
        current = self.get_weight(word, lang)
        new_weight = current + weight_step
        self.data["words"][key] = new_weight
        if debug:
            logger.debug("UserDict confirmation: %s weight → %d", key, new_weight)
        self.flush()

    def flush(self) -> None:
        save_json(self.path, self.data)

    @staticmethod
    def _key(word: str, lang: str) -> str:
        return f"{lang}:{word.lower().strip()}"
