"""Qt main-thread bridge used by platform adapters."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable, TypeVar


T = TypeVar("T")


@dataclass
class _CallRequest:
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    done: threading.Event
    result: Any = None
    error: BaseException | None = None


def ensure_qt_application(argv: list[str] | None = None):
    """Return an existing QApplication or create one in the current thread."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        return app
    return QApplication(argv if argv is not None else sys.argv)


class QtMainThreadInvoker:
    """Synchronous queued-call bridge into Qt's main thread."""

    def __init__(self, app=None):
        from PyQt6.QtCore import QCoreApplication, QObject, Qt, pyqtSignal, pyqtSlot

        class _BridgeObject(QObject):
            call_requested = pyqtSignal(object)

            @pyqtSlot(object)
            def execute(self, request: _CallRequest) -> None:
                try:
                    request.result = request.func(*request.args, **request.kwargs)
                except BaseException as exc:
                    request.error = exc
                finally:
                    request.done.set()

        self._qt = QCoreApplication.instance() if app is None else app
        if self._qt is None:
            raise RuntimeError("QtMainThreadInvoker requires an active Qt application")

        self._bridge = _BridgeObject()
        self._bridge.moveToThread(self._qt.thread())
        self._bridge.call_requested.connect(
            self._bridge.execute,
            Qt.ConnectionType.QueuedConnection,
        )

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T:
        from PyQt6.QtCore import QThread

        if QThread.currentThread() == self._qt.thread():
            return func(*args, **kwargs)

        request = _CallRequest(
            func=func,
            args=args,
            kwargs=kwargs,
            done=threading.Event(),
        )
        self._bridge.call_requested.emit(request)
        if not request.done.wait(timeout):
            raise TimeoutError("Timed out waiting for Qt main-thread call")
        if request.error is not None:
            raise request.error
        return request.result
