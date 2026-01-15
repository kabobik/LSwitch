"""System command wrapper to centralize external process calls.

Provides `run(...)` which delegates to `subprocess.run` and can be
mocked in tests or replaced by alternate implementations.
"""
from __future__ import annotations

import subprocess
from typing import Any
from abc import ABC, abstractmethod


class ISystem(ABC):
    """Abstract interface for system-level operations (xdotool/xclip/xinput).

    Implementations should be small wrappers around subprocess calls and
    are responsible for returning subprocess.CompletedProcess-like objects
    to preserve current expectations in callers.
    """

    @abstractmethod
    def run(self, *popenargs, **kwargs) -> subprocess.CompletedProcess:
        raise NotImplementedError

    @abstractmethod
    def Popen(self, *popenargs, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def xdotool_key(self, sequence: str, timeout: float = 0.3, **kwargs) -> subprocess.CompletedProcess:
        raise NotImplementedError

    @abstractmethod
    def setxkbmap_query(self, timeout: float = 2) -> subprocess.CompletedProcess:
        raise NotImplementedError

    @abstractmethod
    def xinput_list_id(self, name: str, timeout: float = 2) -> subprocess.CompletedProcess:
        raise NotImplementedError

    @abstractmethod
    def xclip_get(self, selection: str = 'primary', timeout: float = 0.5) -> subprocess.CompletedProcess:
        raise NotImplementedError

    @abstractmethod
    def xclip_set(self, text: str, selection: str = 'clipboard', timeout: float = 0.5) -> subprocess.CompletedProcess:
        raise NotImplementedError


class SubprocessSystem(ISystem):
    """Default `ISystem` implementation using subprocess."""

    def run(self, *popenargs, **kwargs) -> subprocess.CompletedProcess:
        return subprocess.run(*popenargs, **kwargs)

    def Popen(self, *popenargs, **kwargs):
        return subprocess.Popen(*popenargs, **kwargs)

    def xdotool_key(self, sequence: str, timeout: float = 0.3, **kwargs) -> subprocess.CompletedProcess:
        return self.run(['xdotool', 'key', sequence], timeout=timeout, **kwargs)

    def setxkbmap_query(self, timeout: float = 2) -> subprocess.CompletedProcess:
        return self.run(['setxkbmap', '-query'], capture_output=True, text=True, timeout=timeout)

    def xinput_list_id(self, name: str, timeout: float = 2) -> subprocess.CompletedProcess:
        return self.run(['xinput', 'list', '--id-only', name], capture_output=True, text=True, timeout=timeout)

    def xclip_get(self, selection: str = 'primary', timeout: float = 0.5) -> subprocess.CompletedProcess:
        return self.run(['xclip', '-o', '-selection', selection], capture_output=True, timeout=timeout, text=True)

    def xclip_set(self, text: str, selection: str = 'clipboard', timeout: float = 0.5) -> subprocess.CompletedProcess:
        return self.run(['xclip', '-selection', selection], input=text, text=True, timeout=timeout)


# Module-level default system instance (can be replaced in tests for DI)
SYSTEM: ISystem = SubprocessSystem()


# Backwards-compatible top-level functions that delegate to the module-level
# `SYSTEM` instance. Tests and callsites that already import `lswitch.system`
# and call `system.run(...)` will continue to work, but code can now set
# `lswitch.system.SYSTEM = MockSystem()` for dependency injection.

def run(*popenargs, **kwargs) -> subprocess.CompletedProcess:
    return SYSTEM.run(*popenargs, **kwargs)


def Popen(*popenargs, **kwargs):
    return SYSTEM.Popen(*popenargs, **kwargs)


# Convenience helpers (small wrappers)
def xdotool_key(sequence: str, timeout: float = 0.3, **kwargs) -> subprocess.CompletedProcess:
    return SYSTEM.xdotool_key(sequence, timeout=timeout, **kwargs)


def setxkbmap_query(timeout: float = 2) -> subprocess.CompletedProcess:
    return SYSTEM.setxkbmap_query(timeout=timeout)


def xinput_list_id(name: str, timeout: float = 2) -> subprocess.CompletedProcess:
    return SYSTEM.xinput_list_id(name, timeout=timeout)


def xclip_get(selection: str = 'primary', timeout: float = 0.5) -> subprocess.CompletedProcess:
    return SYSTEM.xclip_get(selection=selection, timeout=timeout)


def xclip_set(text: str, selection: str = 'clipboard', timeout: float = 0.5) -> subprocess.CompletedProcess:
    return SYSTEM.xclip_set(text=text, selection=selection, timeout=timeout)
