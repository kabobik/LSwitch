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
        self._last_check_time = time.time()
        self._last_mtime = 0.0
        if os.path.exists(self.path):
            self._last_mtime = os.path.getmtime(self.path)

        self.data: dict = load_json(path, {
            "words": {},
        })
        if "words" not in self.data:
            self.data["words"] = {}

    def _check_reload(self) -> None:
        """Перезагружает словарь с диска, если он был изменен (проверка раз в 2.5 сек)."""
        now = time.time()
        if now - self._last_check_time < 2.5:
            return

        self._last_check_time = now

        try:
            if not os.path.exists(self.path):
                return

            current_mtime = os.path.getmtime(self.path)
            if current_mtime > self._last_mtime:
                self._last_mtime = current_mtime
                new_data = load_json(self.path, {"words": {}})
                if "words" not in new_data:
                    new_data["words"] = {}
                self.data = new_data
                logger.info(f"Файл настроек {self.path} был обновлен. Словарь загружен заново.")
        except Exception as e:
            logger.error(f"Ошибка при фоновом обновлении словаря: {e}")

    def get_weight(self, word: str, lang: str) -> int:
        self._check_reload()
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
        try:
            if os.path.exists(self.path):
                self._last_mtime = os.path.getmtime(self.path)
                self._last_check_time = time.time()
        except OSError:
            pass

    @staticmethod
    def _key(word: str, lang: str) -> str:
        return f"{lang}:{word.lower().strip()}"
