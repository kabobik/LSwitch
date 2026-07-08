"""Typed model for the latest automatic conversion."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any


@dataclass
class AutoConversionMarker:
    """Information needed to undo or confirm an automatic conversion."""

    kind: str
    original_word: str
    original_lang: str
    target_lang: str
    direction: str
    word_events: list = field(default_factory=list)
    converted_len: int = 0
    had_space: bool = True
    created_at: float = field(default_factory=time.time)

    @classmethod
    def for_space_conversion(
        cls,
        *,
        original_word: str,
        original_lang: str,
        direction: str,
        word_events: list,
    ) -> "AutoConversionMarker":
        target_lang = "ru" if direction == "en_to_ru" else "en"
        return cls(
            kind="space",
            original_word=original_word,
            original_lang=original_lang,
            target_lang=target_lang,
            direction=direction,
            word_events=list(word_events),
            converted_len=len(word_events),
            had_space=True,
        )

    @classmethod
    def for_mid_word_conversion(
        cls,
        *,
        original_word: str,
        original_lang: str,
        direction: str,
        word_events: list,
    ) -> "AutoConversionMarker":
        target_lang = "ru" if direction == "en_to_ru" else "en"
        return cls(
            kind="mid_word",
            original_word=original_word,
            original_lang=original_lang,
            target_lang=target_lang,
            direction=direction,
            word_events=list(word_events),
            converted_len=len(word_events),
            had_space=False,
        )

    @classmethod
    def from_legacy(cls, marker: "AutoConversionMarker | dict") -> "AutoConversionMarker":
        if isinstance(marker, cls):
            return marker
        direction = str(marker.get("direction") or "")
        original_lang = str(marker.get("lang") or marker.get("original_lang") or "")
        target_lang = str(
            marker.get("target_lang")
            or ("ru" if direction == "en_to_ru" else "en")
        )
        word_events = list(marker.get("word_events") or [])
        return cls(
            kind=str(marker.get("kind") or "space"),
            original_word=str(marker.get("word") or marker.get("original_word") or ""),
            original_lang=original_lang,
            target_lang=target_lang,
            direction=direction,
            word_events=word_events,
            converted_len=int(marker.get("converted_len") or len(word_events)),
            had_space=bool(marker.get("had_space", True)),
            created_at=float(marker.get("time") or marker.get("created_at") or time.time()),
        )

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "word": self.original_word,
            "original_word": self.original_word,
            "lang": self.original_lang,
            "original_lang": self.original_lang,
            "target_lang": self.target_lang,
            "direction": self.direction,
            "word_events": self.word_events,
            "converted_len": self.converted_len,
            "had_space": self.had_space,
            "time": self.created_at,
            "created_at": self.created_at,
        }

    def get(self, key: str, default=None):
        return self.to_legacy_dict().get(key, default)

    def copy(self) -> dict[str, Any]:
        return self.to_legacy_dict().copy()

    def __contains__(self, key: str) -> bool:
        return key in self.to_legacy_dict()

    def __getitem__(self, key: str):
        try:
            return self.to_legacy_dict()[key]
        except KeyError:
            raise KeyError(key)

    def __setitem__(self, key: str, value) -> None:
        if key in {"word", "original_word"}:
            self.original_word = value
        elif key in {"lang", "original_lang"}:
            self.original_lang = value
        elif key == "target_lang":
            self.target_lang = value
        elif key == "direction":
            self.direction = value
        elif key == "word_events":
            self.word_events = value
        elif key == "converted_len":
            self.converted_len = int(value)
        elif key == "had_space":
            self.had_space = bool(value)
        elif key in {"time", "created_at"}:
            self.created_at = float(value)
        elif key == "kind":
            self.kind = value
        else:
            raise KeyError(key)
