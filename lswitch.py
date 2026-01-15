"""Compatibility shim for the project.

This module provides a minimal backwards-compatible top-level import surface
while the real implementation lives in `lswitch/core.py`. It intentionally
keeps behavior small: re-exporting the names other code and tests rely on.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

_ROOT = os.path.dirname(__file__)
_CORE_PATH = os.path.join(_ROOT, 'lswitch', 'core.py')
_SYSTEM_PATH = os.path.join(_ROOT, 'lswitch', 'system.py')

# NOTE (temporary compatibility):
# Historically this project exposed a flat top-level module `lswitch.py` while
# also containing a `lswitch/` package directory. During a refactor we moved
# implementation into the package (e.g. `lswitch/core.py`) but many tests and
# downstream users still import attributes directly from the top-level module
# (for example using `from lswitch import LSwitch` or monkeypatching
# `lswitch.XLIB_AVAILABLE`).
#
# To preserve backwards compatibility during the transition we intentionally
# expose the package directory via `__path__` so imports like `lswitch.xkb`
# resolve to `./lswitch/` instead of the top-level file. This is a *temporary*
# shim and should be removed once consumers have been migrated to import from
# `lswitch` package (issue TBD).
__path__ = [os.path.join(_ROOT, 'lswitch')]


def _load_module_from_path(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


# Load system helper lazily (best-effort)
try:
    system = _load_module_from_path('lswitch.system', _SYSTEM_PATH)
except Exception:
    system = None

# NOTE: keep backwards compatibility for legacy code/tests that import
# `lswitch.system` as a module. They will see whatever `lswitch/system.py`
# exposes (including `SYSTEM` instance defined there).


# Load core symbols eagerly and provide safe fallbacks if import fails.
try:
    _core = _load_module_from_path('lswitch.core', _CORE_PATH)
    LSwitch = _core.LSwitch
    register_instance = _core.register_instance
    force_release_virtual_keyboards = _core.force_release_virtual_keyboards

    # Temporary convenience re-exports -------------------------------------------------
    # For the duration of the refactor we copy public, non-private module-level
    # attributes from `lswitch.core` into this top-level module. This keeps the
    # previous public API surface stable and allows existing tests and callers to
    # patch attributes on `lswitch` (e.g. `lswitch.XLIB_AVAILABLE`, `lswitch.x11_adapter`)
    # as they did before the package split.
    #
    # TODO: remove this copy (and rely on `from lswitch import core as _core` or
    # explicit `from lswitch.core import ...`) once all call sites/tests are
    # updated to import from the package directly.
    for _name in dir(_core):
        if _name.startswith('_'):
            continue
        if _name in globals():
            continue
        globals()[_name] = getattr(_core, _name)
except Exception as exc:  # pragma: no cover - exercised in broken envs
    _err = exc
    def _fail_on_use(*args, **kwargs):
        raise RuntimeError(f"lswitch.core failed to load: {_err}")

    LSwitch = _fail_on_use  # type: ignore
    register_instance = lambda *a, **k: None
    force_release_virtual_keyboards = lambda: 0


__all__ = ['LSwitch', 'register_instance', 'force_release_virtual_keyboards', 'system']


def __getattr__(name: str) -> Any:  # pragma: no cover - defensive
    if name == 'system':
        global system
        if system is None:
            system = _load_module_from_path('lswitch.system', _SYSTEM_PATH)
        return system
    raise AttributeError(f"module 'lswitch' has no attribute '{name}'")


def main(argv=None):
    """Start the application.

    Prefer `core.main()` if provided (some distributions may add an explicit
    entry point). Otherwise, instantiate `LSwitch` and run it. This keeps the
    top-level executable `python -m lswitch` working even though the
    implementation lives in `lswitch/core.py`.
    """
    core = globals().get('_core', None)
    if core and hasattr(core, 'main'):
        return core.main()
    if core and hasattr(core, 'LSwitch'):
        try:
            app = core.LSwitch()
            return app.run()
        except Exception as exc:
            raise RuntimeError(f"lswitch.core failed to start: {exc}")
    raise RuntimeError('Core implementation not available')


if __name__ == '__main__':
    main()
