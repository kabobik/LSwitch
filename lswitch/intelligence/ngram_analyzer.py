"""NgramAnalyzer — scores text by bigram/trigram language probability."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NgramAnalyzer:
    """Computes a language score from bigram and trigram frequencies.

    Higher score = text more likely belongs to target language.
    N-gram data ported from archive/lswitch/ngrams.py.
    """

    def __init__(self):
        self._bigrams_ru: dict[str, float] = {}
        self._bigrams_en: dict[str, float] = {}
        self._trigrams_ru: dict[str, float] = {}
        self._trigrams_en: dict[str, float] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            from lswitch.intelligence.bigrams import BIGRAMS_RU, BIGRAMS_EN
            self._bigrams_ru = BIGRAMS_RU
            self._bigrams_en = BIGRAMS_EN
        except ImportError:
            pass
        try:
            from lswitch.intelligence.trigrams import TRIGRAMS_RU, TRIGRAMS_EN
            self._trigrams_ru = TRIGRAMS_RU
            self._trigrams_en = TRIGRAMS_EN
        except ImportError:
            pass
        self._loaded = True

    def score(self, text: str, lang: str) -> float:
        """Return a normalised language score [0..1] for `text` in `lang`."""
        self._ensure_loaded()
        text = text.lower()
        bigrams = self._bigrams_ru if lang == "ru" else self._bigrams_en
        trigrams = self._trigrams_ru if lang == "ru" else self._trigrams_en

        total = 0.0
        count = 0

        for i in range(len(text) - 1):
            bg = text[i:i + 2]
            total += bigrams.get(bg, 0.0)
            count += 1

        for i in range(len(text) - 2):
            tg = text[i:i + 3]
            total += trigrams.get(tg, 0.0) * 3  # weight trigrams higher
            count += 1

        return total / max(count, 1)

    def should_convert(self, text: str, from_lang: str, threshold: float = 0.1) -> bool:
        """Return True if text scores better in the opposite language.

        Guards:
        - text containing digits or non-letter characters → False
          (numbers, passwords, abbreviations with special chars)
        - short sequences ≤ 3 chars with zero n-gram matches → False
          (abbreviations like php/sql that are too short to discriminate)
        """
        if not text:
            return False
        # Не конвертировать если есть цифры или спецсимволы
        clean = text.strip().lower()
        if not clean.isalpha():
            return False
        self._ensure_loaded()
        to_lang = "en" if from_lang == "ru" else "ru"
        score_from = self.score(clean, from_lang)
        score_to = self.score(clean, to_lang)
        # Основное правило: целевой язык значительно лучше
        if score_to - score_from > threshold:
            return True
        # Эвристика: нет совпадений в from_lang и текст достаточно длинный
        # (>= 4 符合: исключает короткие аббревиатуры php/sql, но ловит ghbdtn)
        if score_from == 0.0 and len(clean) >= 4:
            return True
        return False
