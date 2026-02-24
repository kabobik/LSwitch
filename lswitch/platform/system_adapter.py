"""ISystemAdapter interface — abstraction for subprocess/system calls."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class ISystemAdapter(ABC):
    @abstractmethod
    def run_command(self, args: list[str], timeout: float = 1.0) -> CommandResult: ...

    @abstractmethod
    def xdotool_key(self, sequence: str, timeout: float = 0.3) -> None: ...

    @abstractmethod
    def get_clipboard(self, selection: str = "primary") -> str: ...

    @abstractmethod
    def set_clipboard(self, text: str, selection: str = "clipboard") -> None: ...
