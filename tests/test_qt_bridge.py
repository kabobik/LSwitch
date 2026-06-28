"""Tests for main-thread invokers."""

from __future__ import annotations

import importlib
import sys
import threading
import time
from contextlib import contextmanager

import pytest

from lswitch.platform.main_thread import DirectMainThreadInvoker


@contextmanager
def _real_qtcore():
    """Temporarily bypass test_ui.py's PyQt6 sys.modules mocks."""
    module_names = [
        name for name in sys.modules
        if name == "PyQt6" or name.startswith("PyQt6.")
    ]
    saved = {name: sys.modules[name] for name in module_names}
    for name in module_names:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()

    try:
        try:
            qtcore = importlib.import_module("PyQt6.QtCore")
        except ImportError:
            pytest.skip("real PyQt6.QtCore is not available")
        if not hasattr(qtcore, "QCoreApplication") or not hasattr(qtcore, "QThread"):
            pytest.skip("real PyQt6.QtCore is not available")
        yield qtcore
    finally:
        for name in [
            mod_name for mod_name in sys.modules
            if mod_name == "PyQt6" or mod_name.startswith("PyQt6.")
        ]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


class TestDirectMainThreadInvoker:
    def test_call_returns_result(self):
        invoker = DirectMainThreadInvoker()

        assert invoker.call(lambda a, b: a + b, 2, 3) == 5

    def test_call_propagates_exception(self):
        invoker = DirectMainThreadInvoker()

        with pytest.raises(ValueError, match="boom"):
            invoker.call(lambda: (_ for _ in ()).throw(ValueError("boom")))


class TestQtMainThreadInvoker:
    def test_call_from_qt_thread_runs_directly(self):
        with _real_qtcore() as qtcore:
            app = qtcore.QCoreApplication.instance() or qtcore.QCoreApplication([])

            from lswitch.ui.qt_bridge import QtMainThreadInvoker

            invoker = QtMainThreadInvoker(app)

            assert invoker.call(lambda: 42) == 42

    def test_call_from_worker_runs_on_qt_thread(self):
        with _real_qtcore() as qtcore:
            app = qtcore.QCoreApplication.instance() or qtcore.QCoreApplication([])

            from lswitch.ui.qt_bridge import QtMainThreadInvoker

            invoker = QtMainThreadInvoker(app)
            main_thread_id = threading.get_ident()
            result: dict[str, int] = {}
            errors: list[BaseException] = []

            def worker() -> None:
                try:
                    result["thread_id"] = invoker.call(threading.get_ident, timeout=1.0)
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=worker)
            thread.start()
            deadline = time.time() + 1.5
            while thread.is_alive() and time.time() < deadline:
                app.processEvents()
                thread.join(0.01)

            thread.join(timeout=0.1)

            assert errors == []
            assert result["thread_id"] == main_thread_id
