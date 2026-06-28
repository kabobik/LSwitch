"""Main-thread invocation abstractions for platform adapters."""

from __future__ import annotations

from typing import Any, Callable, Protocol, TypeVar


T = TypeVar("T")


class MainThreadInvoker(Protocol):
    """Runs callables on the runtime's main/UI thread."""

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T: ...


class DirectMainThreadInvoker:
    """Invoker for code paths that are already safe to run directly."""

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T:
        return func(*args, **kwargs)
