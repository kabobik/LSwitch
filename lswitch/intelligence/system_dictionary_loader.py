"""Optional Hunspell/MySpell dictionary loader for prefix indexes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadedSystemDictionary:
    lang: str
    path: Path
    words: set[str]


class SystemDictionaryLoader:
    """Loads plain word forms from Hunspell/MySpell .dic files."""

    DEFAULT_DIRS = (
        Path("/usr/share/hunspell"),
        Path("/usr/share/myspell/dicts"),
        Path("/usr/share/myspell"),
    )
    CANDIDATE_PREFIXES = {
        "en": ("en_US", "en_GB", "en"),
        "ru": ("ru_RU", "ru"),
    }
    ENCODINGS = ("utf-8-sig", "utf-8", "cp1251", "koi8-r", "iso-8859-1")

    def __init__(
        self,
        *,
        dictionary_dirs: Iterable[str | Path] | None = None,
        explicit_paths: dict[str, str | Path] | None = None,
        min_word_len: int = 1,
    ):
        self.dictionary_dirs = tuple(
            Path(path) for path in (dictionary_dirs or self.DEFAULT_DIRS)
        )
        self.explicit_paths = {
            lang: Path(path)
            for lang, path in (explicit_paths or {}).items()
            if path
        }
        self.min_word_len = max(1, min_word_len)

    def load(self, lang: str) -> LoadedSystemDictionary | None:
        path = self.find_dictionary(lang)
        if path is None:
            logger.info("No system dictionary found for lang=%s", lang)
            return None

        words = self.load_words(lang, path)
        logger.info(
            "Loaded %d words for lang=%s from %s",
            len(words),
            lang,
            path,
        )
        return LoadedSystemDictionary(lang=lang, path=path, words=words)

    def load_words(self, lang: str, path: str | Path) -> set[str]:
        dictionary_path = Path(path)
        words: set[str] = set()
        for index, line in enumerate(self._read_lines(dictionary_path)):
            token = line.strip()
            if not token or token.startswith("#"):
                continue
            if index == 0 and token.isdigit():
                continue

            word = token.split("/", 1)[0].strip().lower()
            if len(word) < self.min_word_len:
                continue
            if self._valid_word(lang, word):
                words.add(word)
        return words

    def find_dictionary(self, lang: str) -> Path | None:
        explicit = self.explicit_paths.get(lang)
        if explicit is not None:
            return explicit if explicit.is_file() else None

        prefixes = self.CANDIDATE_PREFIXES.get(lang, ())
        candidates: list[tuple[int, str, Path]] = []
        for directory in self.dictionary_dirs:
            if not directory.is_dir():
                continue
            for path in directory.glob("*.dic"):
                score = self._candidate_score(path.stem, prefixes)
                if score is not None:
                    candidates.append((score, path.name, path))

        if not candidates:
            return None
        return sorted(candidates)[0][2]

    def _read_lines(self, path: Path) -> list[str]:
        last_error: UnicodeDecodeError | None = None
        for encoding in self.ENCODINGS:
            try:
                return path.read_text(encoding=encoding).splitlines()
            except UnicodeDecodeError as exc:
                last_error = exc
        if last_error is not None:
            logger.warning(
                "Falling back to replacement decoding for %s after %s",
                path,
                last_error,
            )
        return path.read_text(encoding="utf-8", errors="replace").splitlines()

    @classmethod
    def _candidate_score(
        cls,
        stem: str,
        prefixes: tuple[str, ...],
    ) -> int | None:
        stem_lower = stem.lower()
        for index, prefix in enumerate(prefixes):
            if stem_lower == prefix.lower():
                return index
        for index, prefix in enumerate(prefixes):
            if stem_lower.startswith(prefix.lower()):
                return len(prefixes) + index
        return None

    @staticmethod
    def _valid_word(lang: str, word: str) -> bool:
        if lang == "en":
            return all("a" <= char <= "z" for char in word)
        if lang == "ru":
            return all(("а" <= char <= "я") or char == "ё" for char in word)
        return False
