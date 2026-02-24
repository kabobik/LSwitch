# Refactor Cleanup: Issue checklist

This document lists small, focused issues to remove temporary compatibility shims and re-exports introduced during the refactor. Each entry is written as an issue template (title + body + acceptance criteria) suitable for creating a GitHub issue or filing a small PR.

---

## Meta issue: Remove temporary compatibility shim and re-exports

Title: [refactor] Remove temporary compatibility shim from `lswitch.py`

Description:
- Remove `__path__` override and the re-export loop in `lswitch.py` that copies public attributes from `lswitch.core` to the top-level module. These were intentionally added as a temporary compatibility layer during refactor.

Acceptance criteria:
- `lswitch.py` contains only a minimal shim (or is removed) and no longer manipulates `__path__` or re-exports core symbols.
- All tests and code paths that used to rely on top-level copies are updated to import from package modules.
- `tests/test_shim_documentation.py` is removed or updated appropriately.
- CI is green and a follow-up issue tracks remaining migration work.

Suggested labels: `refactor`, `cleanup`, `high-impact`

---

## Per-module small issues

Below are per-module issues that are small and self-contained. Aim to make each one a single PR that modifies only one or two files and includes tests.

### 1) `lswitch` package imports and tests

Title: [chore] Update tests to import from `lswitch` package modules

Body:
- Find tests that rely on top-level attributes (e.g. `lswitch.XLIB_AVAILABLE`, `lswitch.x11_adapter`) and change them to import from the proper package module (e.g. `from lswitch import core as _core; _core.XLIB_AVAILABLE` or `from lswitch import xkb`).

Acceptance criteria:
- Tests no longer depend on the shim internals.
- No behavior changes; all tests pass.

Labels: `test`, `low-risk`

---

### 2) `lswitch/core.py` re-exports

Title: [refactor] Stop relying on re-exported symbols on `lswitch` top-level

Body:
- Replace code that uses top-level re-exports with direct imports from `lswitch.core` or the correct module.
- Remove any analogues of the re-export pattern in other modules.

Acceptance criteria:
- No code uses `from lswitch import x11_adapter` if `x11_adapter` lives in `lswitch.core` (update to `from lswitch.core import x11_adapter` or equivalent).

Labels: `refactor`, `low-risk`

---

### 3) `adapters` / X11 adapter consolidation

Title: [refactor] Make `adapters.*` importable from package and update tests

Body:
- Ensure tests import adapters with `from lswitch.adapters import x11 as x11_adapter` or `import lswitch.adapters.x11 as x11_adapter` instead of reaching through top-level shims.
- If any adapters depended on `lswitch` top-level shims, adjust them to use dependency injection where appropriate.

Acceptance criteria:
- Adapter tests use package imports; no test imports `x11_adapter` from top-level module.

Labels: `refactor`, `adapters`

---

### 4) `lswitch/system.py` and subprocess wrappers

Title: [refactor] Use `lswitch.system` directly and remove shim fallback

Body:
- Ensure code uses `from lswitch import system` (the package module) or `from lswitch.system import run as system_run` explicitly rather than relying on top-level `system` re-export.
- Remove fallback behaviors in `lswitch.py` shim that attempted to lazy-load system; callers should import actual package module.

Acceptance criteria:
- All call sites import `lswitch.system` or the specific functions they use.
- Tests that previously relied on monkeypatching `lswitch.system` are updated to patch `lswitch.system` module in place.

Labels: `refactor`, `system`

---

### 5) `lswitch/input.py` cleanup

Title: [refactor] Finalize `InputHandler` as canonical event handler and remove legacy fallbacks

Body:
- Ensure `LSwitch` delegates to `InputHandler` by default and remove legacy handling paths that duplicate logic.
- Update tests to target `InputHandler` directly when appropriate.

Acceptance criteria:
- Legacy duplicated code paths are removed or delegated.
- Tests cover `InputHandler` behavior; adjustments to LSwitch tests preserve behavior.

Labels: `refactor`, `input`

---

### 6) `lswitch/monitor.py` and thread start/stop

Title: [refactor] Deprecate legacy thread start fallback and rely on `LayoutMonitor`

Body:
- Stop creating fallback legacy threads in `core` when `LayoutMonitor` is available; instead instantiate and rely on `LayoutMonitor`'s start/stop semantics.
- Remove any `layout_thread` / `layouts_file_monitor_thread` attributes if they are only kept for shim compatibility, or keep but document they are proxies to `LayoutMonitor` threads.

Acceptance criteria:
- `LayoutMonitor` is the single source of truth for background monitoring threads.
- Tests patch `LayoutMonitor` behavior via its public API rather than monkeypatching legacy attributes.

Labels: `refactor`, `monitor`

---

### 7) `lswitch/conversion` / `ConversionManager`

Title: [refactor] Move remaining conversion helper logic into `ConversionManager` and remove legacy helpers

Body:
- Consolidate conversion logic fully into `ConversionManager` and remove legacy helper functions from top-level or `core` that were left behind.
- Ensure tests target `ConversionManager` and maintain public behavior.

Acceptance criteria:
- All conversion logic is reachable via `ConversionManager` public API.
- No lingering `convert_and_retype` or `check_and_auto_convert` helpers remain in `lswitch.py`/`core.py` outside of `ConversionManager`.

Labels: `refactor`, `conversion`

---

### 8) Cleanup tests that assert shim behaviour

Title: [chore] Remove or rewrite tests that relied on shim internals

Body:
- Remove `tests/test_shim_documentation.py` or rewrite it to assert package-level import behavior rather than shim internals.
- Replace assertions like `assert hasattr(lswitch, 'x11_adapter')` with `assert hasattr(lswitch.core, 'x11_adapter')` or equivalent.

Acceptance criteria:
- Tests no longer depend on temporary shim behavior.
- Test coverage is preserved or improved.

Labels: `test`, `cleanup`

---

### 9) Documentation & deprecation notes

Title: [docs] Add migration notes for removing shim compatibility

Body:
- Add a short guide in `docs/` describing the migration from top-level imports to package imports and list common replacements.
- Mention timeline and link to meta issue.

Acceptance criteria:
- `docs/MIGRATION.md` (or similar) includes search/replace examples and a plan.

Labels: `docs` 

---

## How to use this list
- Copy any section above to a new GitHub Issue, link to the meta issue and then open a small PR that addresses only that section.
- Prefer small PRs (single module, several tests) and include a note referencing this checklist and the meta-issue.

---

If you'd like, I can open local issue stubs as files in `.github/ISSUE_STUBS/` (one file per issue) so you can quickly create them on GitHub or paste bodies into the web UI. Let me know if you'd like that automation. 
