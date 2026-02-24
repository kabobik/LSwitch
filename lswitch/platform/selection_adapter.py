"""ISelectionAdapter interface and SelectionInfo dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SelectionInfo:
    text: str
    owner_id: int       # XGetSelectionOwner window ID
    timestamp: float    # Time of retrieval


class ISelectionAdapter(ABC):
    @abstractmethod
    def get_selection(self) -> SelectionInfo: ...

    @abstractmethod
    def has_fresh_selection(self, threshold: float = 0.5) -> bool: ...

    @abstractmethod
    def replace_selection(self, new_text: str) -> bool: ...

    @abstractmethod
    def expand_selection_to_word(self) -> SelectionInfo: ...
