"""AutoDetector — integrates DictionaryService and NgramAnalyzer for layout detection."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lswitch.intelligence.dictionary_service import DictionaryService
    from lswitch.intelligence.ngram_analyzer import NgramAnalyzer
    from lswitch.intelligence.user_dictionary import UserDictionary

logger = logging.getLogger(__name__)


class AutoDetector:
    """Decides whether a word needs layout conversion.

    Priority chain (from TECHNICAL_SPEC_v2.md §6.2):
    1. Word correct in current layout dict → no convert
    2. Converted word found in target layout dict → convert
    3. N-gram score significantly better in target → convert
    4. Otherwise → no convert
    """

    def __init__(self, dictionary: "DictionaryService", ngrams: "NgramAnalyzer",
                 user_dict: "UserDictionary | None" = None):
        self.dictionary = dictionary
        self.ngrams = ngrams
        self.user_dict = user_dict

    def should_convert(self, word: str | None, current_layout: str) -> tuple[bool, str]:
        """Return (should_convert, reason).

        Args:
            word: the word as typed (e.g. "ghbdtn"), or None.
            current_layout: layout the word was typed in ("en" or "ru").

        Returns:
            (should_convert: bool, reason: str)
        """
        # Guard: None or non-string
        if not isinstance(word, str):
            return (False, "empty or invalid input")

        word_clean = word.strip()
        if not word_clean:
            return (False, "empty input")

        # Guard: reject words that contain characters which are neither
        # alphabetic nor valid "letter keys" for the given layout.
        # On EN keyboard ',' / '.' / ';' etc. are the physical keys for
        # Cyrillic letters б / ю / ж — they must not block conversion.
        from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN
        if current_layout == "en":
            if not all(c.isalpha() or EN_TO_RU.get(c.lower(), "").isalpha()
                       for c in word_clean):
                return (False, "non-alphabetic input")
        elif current_layout == "ru":
            if not all(c.isalpha() or RU_TO_EN.get(c.lower(), "").isalpha()
                       for c in word_clean):
                return (False, "non-alphabetic input")
        else:
            if not word_clean.isalpha():
                return (False, "non-alphabetic input")

        # Priority 1 & 2: dictionary-based detection
        dict_convert, dict_reason = self.dictionary.should_convert(word_clean, current_layout)

        # Priority 1: word is already correct → keep as-is
        if not dict_convert and "already correct" in dict_reason:
            return (False, dict_reason)

        # Priority 1.5: UserDictionary protection
        if self.user_dict:
            w_lower = word_clean.lower()
            if self.user_dict.is_protected(w_lower, current_layout):
                return (False, "user_dict: temporarily protected")
            weight = self.user_dict.get_weight(w_lower, current_layout)
            min_w = self.user_dict.data.get('settings', {}).get('min_weight', 2)
            if weight <= -min_w:
                return (False, f"user_dict: weight={weight} <= -{min_w}")

        # Priority 2: converted form is a known word → convert
        if dict_convert:
            return (True, dict_reason)

        # Priority 3: N-gram analysis on the converted text
        w = word_clean.lower()
        if current_layout == "en":
            converted = "".join(EN_TO_RU.get(c, c) for c in w)
            score_target = self.ngrams.score(converted, "ru")
            score_source = self.ngrams.score(w, "en")
        elif current_layout == "ru":
            converted = "".join(RU_TO_EN.get(c, c) for c in w)
            score_target = self.ngrams.score(converted, "en")
            score_source = self.ngrams.score(w, "ru")
        else:
            return (False, f"unknown layout: {current_layout}")

        threshold = 0.05
        if score_target - score_source > threshold:
            return (True, f"ngram: target={score_target:.3f} > source={score_source:.3f}")

        # Heuristic: zero source score + long enough word → likely wrong layout
        if score_source == 0.0 and len(w) >= 4:
            return (True, "ngram: zero source score, likely wrong layout")

        return (False, "no evidence of wrong layout")
