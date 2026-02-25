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
    """Stores word weights: >0 = prefer EN, <0 = prefer RU.

    |weight| >= threshold triggers auto-conversion suppression.
    """

    DEFAULT_SETTINGS = {
        "min_weight": 2,
        "correction_timeout": 5.0,
        "threshold": 5,
    }

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self.data: dict = load_json(path, {
            "words": {},
            "settings": dict(self.DEFAULT_SETTINGS),
        })
        if "words" not in self.data:
            self.data["words"] = {}
        if "settings" not in self.data:
            self.data["settings"] = dict(self.DEFAULT_SETTINGS)

    def get_weight(self, word: str, lang: str) -> int:
        key = self._key(word, lang)
        return self.data["words"].get(key, {}).get("weight", 0)

    def is_protected(self, word: str, lang: str) -> bool:
        """Return True if the word is temporarily protected from auto-conversion."""
        key = self._key(word, lang)
        entry = self.data["words"].get(key, {})
        protected_until = entry.get("protected_until", 0)
        return time.time() < protected_until

    def add_correction(self, word: str, lang: str, debug: bool = False) -> None:
        """Penalise auto-conversion for this word (-1 weight) and set protection."""
        key = self._key(word, lang)
        entry = self.data["words"].setdefault(key, {"weight": 0})
        entry["weight"] -= 1
        # Temporarily protect word from auto-conversion
        timeout = self.data["settings"].get("correction_timeout", 5.0)
        entry["protected_until"] = time.time() + timeout
        if debug:
            logger.debug("UserDict correction: %s weight → %d, protected for %.1fs", key, entry["weight"], timeout)
        self.flush()

    def add_confirmation(self, word: str, lang: str, debug: bool = False) -> None:
        """Confirm auto-conversion was correct (+1 weight)."""
        key = self._key(word, lang)
        entry = self.data["words"].setdefault(key, {"weight": 0})
        entry["weight"] += 1
        if debug:
            logger.debug("UserDict confirmation: %s weight → %d", key, entry["weight"])
        self.flush()

    def flush(self) -> None:
        save_json(self.path, self.data)

    @staticmethod
    def _key(word: str, lang: str) -> str:
        return f"{lang}:{word.lower().strip()}"
