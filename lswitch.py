"""Compatibility shim for the project.

This module provides a minimal backwards-compatible top-level import surface
while the real implementation lives in `lswitch/core.py`. It intentionally
keeps behavior small: re-exporting the names other code and tests rely on.
"""

from __future__ import annotations

import importlib.util
import os
import sys
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


# System helper will be loaded lazily on demand (see `__getattr__`).
system = None


# We defer loading of the full core implementation until it's first needed.
# This avoids import-time side-effects when the top-level shim is executed as
# a script (which could otherwise shadow the `lswitch` package name and
# interfere with package imports in installed environments).
_core = None
_err = None

def _ensure_core_loaded():
    """Load the `lswitch.core` module and populate top-level exports."""
    global _core, _err, LSwitch, register_instance, force_release_virtual_keyboards
    if _core is not None or _err is not None:
        return
    try:
        _core = _try_import_core()
        LSwitch = _core.LSwitch
        register_instance = _core.register_instance
        force_release_virtual_keyboards = _core.force_release_virtual_keyboards

        # Temporary convenience re-exports -------------------------------------------------
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


def _try_import_core():
    # Before trying the standard import, ensure common install paths are
    # present on sys.path and avoid the case where the top-level script file
    # shadows the package module name (i.e., `lswitch` as a simple module).
    try:
        alt_lib = '/usr/local/lib/lswitch'
        if os.path.isdir(alt_lib) and alt_lib not in sys.path:
            sys.path.insert(0, alt_lib)
        # If a non-package `lswitch` module is already loaded (the script),
        # remove it so importlib can find the real package.
        existing = sys.modules.get('lswitch')
        if existing is not None and not getattr(existing, '__path__', None):
            try:
                del sys.modules['lswitch']
            except Exception:
                pass
    except Exception as e:
        print(f"lswitch: error preparing sys.path: {e}", file=sys.stderr, flush=True)

    # 1) Try standard import (works when the package is installed on sys.path)
    try:
        import importlib
        m = importlib.import_module('lswitch.core')
        return m
    except Exception as e:
        print(f"lswitch: import lswitch.core failed: {e}", file=sys.stderr, flush=True)

    # 2) Try loading from path relative to this script (legacy behavior)
    try:
        return _load_module_from_path('lswitch.core', _CORE_PATH)
    except Exception as e:
        print(f"lswitch: load from _CORE_PATH failed ({_CORE_PATH}): {e}", file=sys.stderr, flush=True)

    # 3) Try common install locations (e.g., /usr/local/lib/lswitch/lswitch/core.py)
    try:
        alt_pkg_dir = os.path.join('/usr/local/lib/lswitch', 'lswitch')
        alt_init = os.path.join(alt_pkg_dir, '__init__.py')
        alt_core = os.path.join(alt_pkg_dir, 'core.py')
        # If a package exists in alt location, load it as the real `lswitch` package
        if os.path.isdir(alt_pkg_dir) and os.path.exists(alt_init):
            try:
                # Load package __init__ as `lswitch` to avoid import collisions with
                # the top-level script (which may already be named `lswitch`).
                spec = importlib.util.spec_from_file_location('lswitch', alt_init)
                pkg = importlib.util.module_from_spec(spec)
                # Remove any existing `lswitch` entries to avoid shadowing by the
                # top-level script or partial imports. Be conservative and remove
                # only lswitch-related entries.
                for _k in list(sys.modules.keys()):
                    if _k == 'lswitch' or _k.startswith('lswitch.'):
                        try:
                            del sys.modules[_k]
                        except Exception:
                            pass
                # Ensure any imports during package initialization see this module
                sys.modules['lswitch'] = pkg
                pkg.__path__ = [alt_pkg_dir]
                spec.loader.exec_module(pkg)  # type: ignore[attr-defined]
                m = importlib.import_module('lswitch.core')
                return m
            except Exception as e:
                print(f"lswitch: load package from alt location failed ({alt_pkg_dir}): {e}", file=sys.stderr, flush=True)
        # Fallback: if core.py exists directly, try loading the module (less ideal)
        if os.path.exists(alt_core):
            try:
                return _load_module_from_path('lswitch.core', alt_core)
            except Exception as e:
                print(f"lswitch: load from alt path failed ({alt_core}): {e}", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"lswitch: error while checking alt paths under /usr/local/lib/lswitch: {e}", file=sys.stderr, flush=True)

    # 4) No core found
    raise ImportError('Core implementation not found in known locations')

try:
    _core = _try_import_core()
    LSwitch = _core.LSwitch
    register_instance = _core.register_instance
    force_release_virtual_keyboards = _core.force_release_virtual_keyboards

    # Temporary convenience re-exports -------------------------------------------------
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
    # Lazily load the `system` helper when requested
    if name == 'system':
        global system
        if system is None:
            try:
                system = _load_module_from_path('lswitch.system', _SYSTEM_PATH)
            except Exception:
                system = None
        return system

    # For all other attributes, ensure the core implementation is loaded and
    # delegate attribute access to it.
    _ensure_core_loaded()
    if _core is not None and hasattr(_core, name):
        return getattr(_core, name)

    raise AttributeError(f"module 'lswitch' has no attribute '{name}'")


def main(argv=None):
    """Start the application.

    Prefer `core.main()` if provided (some distributions may add an explicit
    entry point). Otherwise, instantiate `LSwitch` and run it. This keeps the
    top-level executable `python -m lswitch` working even though the
    implementation lives in `lswitch/core.py`.
    """
    _ensure_core_loaded()
    if _core and hasattr(_core, 'main'):
        return _core.main()
    if _core and hasattr(_core, 'LSwitch'):
        try:
            app = _core.LSwitch()
            return app.run()
        except Exception as exc:
            raise RuntimeError(f"lswitch.core failed to start: {exc}")
    raise RuntimeError('Core implementation not available')


if __name__ == '__main__':
    main()
