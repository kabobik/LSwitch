"""IXKBAdapter interface and LayoutInfo dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LayoutInfo:
    name: str       # 'en', 'ru'
    index: int      # XKB group index: 0, 1, ...
    xkb_name: str   # 'us', 'ru' (for setxkbmap)


class IXKBAdapter(ABC):
    @abstractmethod
    def get_layouts(self) -> list[LayoutInfo]: ...

    @abstractmethod
    def get_current_layout(self) -> LayoutInfo: ...

    @abstractmethod
    def switch_layout(self, target: Optional[LayoutInfo] = None) -> LayoutInfo: ...

    @abstractmethod
    def keycode_to_char(self, keycode: int, layout: LayoutInfo, shift: bool = False) -> str: ...
