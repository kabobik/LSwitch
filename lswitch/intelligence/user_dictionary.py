"""UserDictionary — per-user layout decision learning.

The on-disk TOML format stores positive confidence counters in two explicit
action groups:

    [convert.en]  # typed in EN layout and should be converted
    [keep.en]     # typed in EN layout and should be kept as-is

``get_weight()`` keeps the older signed API for AutoDetector:
``convert_weight - keep_weight``.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import logging

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - guarded by package metadata
    tomllib = None

logger = logging.getLogger(__name__)

DEFAULT_PATH = os.path.expanduser("~/.config/lswitch/user_dict.toml")
_ACTIONS = ("convert", "keep")
_LANGS = ("en", "ru")


class UserDictionary:
    """Stores user decisions for typed words by input layout."""

    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self._last_check_time = time.time()
        self._last_mtime = 0.0
        if os.path.exists(self.path):
            self._last_mtime = os.path.getmtime(self.path)

        self.data: dict = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path) or tomllib is None:
            return self._empty_data()

        try:
            with open(self.path, "rb") as f:
                raw = tomllib.load(f)
        except Exception as exc:
            logger.warning("Could not read user dictionary %s: %s", self.path, exc)
            return self._empty_data()

        return self._normalize_data(raw)

    def _check_reload(self) -> None:
        """Reload the dictionary if the file changed on disk."""
        now = time.time()
        if not hasattr(self, "_last_check_time"):
            self._last_check_time = now
        if not hasattr(self, "_last_mtime"):
            self._last_mtime = 0.0
        if now - self._last_check_time < 2.5:
            return

        self._last_check_time = now

        try:
            if not os.path.exists(self.path):
                return

            current_mtime = os.path.getmtime(self.path)
            if current_mtime > self._last_mtime:
                self._last_mtime = current_mtime
                self.data = self._load()
                logger.info("User dictionary %s was reloaded.", self.path)
        except Exception as exc:
            logger.error("User dictionary reload failed: %s", exc)

    def get_weight(self, word: str, lang: str) -> int:
        """Return signed effective weight: convert confidence minus keep confidence."""
        self._check_reload()
        word_key = self._word(word)
        lang_key = self._lang(lang)
        convert_weight = self._get_action_weight("convert", lang_key, word_key)
        keep_weight = self._get_action_weight("keep", lang_key, word_key)
        return convert_weight - keep_weight

    def add_correction(
        self,
        word: str,
        lang: str,
        debug: bool = False,
        weight_step: int = 2,
    ) -> None:
        """Record that this typed word should be kept as-is."""
        new_weight = self._increment("keep", word, lang, weight_step)
        effective = self._effective_weight(word, lang)
        if debug:
            logger.debug(
                "UserDict keep: %s:%s weight=%d effective=%d",
                self._lang(lang),
                self._word(word),
                new_weight,
                effective,
            )
        self.flush()

    def add_confirmation(
        self,
        word: str,
        lang: str,
        debug: bool = False,
        weight_step: int = 1,
    ) -> None:
        """Record that this typed word should be converted."""
        new_weight = self._increment("convert", word, lang, weight_step)
        effective = self._effective_weight(word, lang)
        if debug:
            logger.debug(
                "UserDict convert: %s:%s weight=%d effective=%d",
                self._lang(lang),
                self._word(word),
                new_weight,
                effective,
            )
        self.flush()

    def flush(self) -> None:
        self._save()
        try:
            if os.path.exists(self.path):
                self._last_mtime = os.path.getmtime(self.path)
                self._last_check_time = time.time()
        except OSError:
            pass

    def _increment(self, action: str, word: str, lang: str, weight_step: int) -> int:
        weight_step = max(1, int(weight_step))
        table = self._table(action, self._lang(lang))
        word_key = self._word(word)
        table[word_key] = int(table.get(word_key, 0)) + weight_step
        return table[word_key]

    def _get_action_weight(self, action: str, lang: str, word: str) -> int:
        return int(self._table(action, lang).get(word, 0))

    def _effective_weight(self, word: str, lang: str) -> int:
        word_key = self._word(word)
        lang_key = self._lang(lang)
        return (
            self._get_action_weight("convert", lang_key, word_key)
            - self._get_action_weight("keep", lang_key, word_key)
        )

    def _table(self, action: str, lang: str) -> dict:
        self.data = self._normalize_data(getattr(self, "data", None))
        action_table = self.data.setdefault(action, {})
        return action_table.setdefault(lang, {})

    def _save(self) -> None:
        dir_path = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(dir_path, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".toml.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self._dump_toml())
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _dump_toml(self) -> str:
        lines = [
            "# LSwitch user dictionary",
            "# Values are confidence counters.",
            "# Effective decision score: convert weight - keep weight.",
            "",
        ]

        for action in _ACTIONS:
            for lang in _LANGS:
                words = self._table(action, lang)
                if not words:
                    continue
                lines.append(f"[{action}.{lang}]")
                for word in sorted(words):
                    lines.append(f"{json.dumps(word, ensure_ascii=False)} = {int(words[word])}")
                lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _empty_data() -> dict:
        return {
            action: {lang: {} for lang in _LANGS}
            for action in _ACTIONS
        }

    @classmethod
    def _normalize_data(cls, data) -> dict:
        normalized = cls._empty_data()
        if not isinstance(data, dict):
            return normalized

        for action in _ACTIONS:
            action_data = data.get(action, {})
            if not isinstance(action_data, dict):
                continue
            for lang, words in action_data.items():
                lang_key = cls._lang(lang)
                if not isinstance(words, dict):
                    continue
                table = normalized.setdefault(action, {}).setdefault(lang_key, {})
                for word, weight in words.items():
                    try:
                        weight_int = int(weight)
                    except (TypeError, ValueError):
                        continue
                    if weight_int > 0:
                        table[cls._word(word)] = weight_int

        return normalized

    @staticmethod
    def _word(word: str) -> str:
        return str(word).lower().strip()

    @staticmethod
    def _lang(lang: str) -> str:
        return str(lang).lower().strip()
