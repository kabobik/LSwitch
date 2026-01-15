---
name: "Refactor: remove temporary compatibility shim"
about: "Track removal of temporary compatibility shims and re-exports after refactor completion"
title: "[refactor] Remove temporary compatibility shim and related work"
labels: "refactor, cleanup"
assignees: ""
---

## Summary

This issue tracks the final cleanup tasks to remove temporary compatibility
workarounds introduced during the package refactor (see `lswitch.py` shim).
These workarounds were intentionally added to keep the codebase runnable
while migrating implementation into `lswitch/` package. They must be removed
once callers/tests import from the package directly.

## Locations to inspect
- `lswitch.py`:
  - `__path__` override (temporary package shim)
  - Re-export loop that copies public names from `lswitch.core`
  - Comments marked `NOTE (temporary compatibility)` or `TODO: remove`
- `lswitch/core.py`, `lswitch/monitor.py`, and other modules for `TODO:` markers
- Tests that intentionally assert shim behavior (e.g. `tests/test_shim_documentation.py`)

## Acceptance criteria ✅
- Remove shim code and compatibility re-exports from `lswitch.py`.
- Update any call sites/tests to import directly from `lswitch` package, e.g.
  `from lswitch.core import LSwitch` or `from lswitch import LSwitch` where package behavior is used.
- Remove or update tests that assert shim internals (e.g. `x11_adapter` on top-level module).
- All unit tests pass locally and in CI (no regressions, maintain coverage where applicable).
- Update docs/CHANGELOG with migration notes and a brief developer guide.

## Suggested cleanup steps
1. Search for markers: `TODO: remove`, `NOTE (temporary compatibility)`, `shim`, `re-export`.
2. Convert any callers referencing shim internals to import from package modules.
3. Remove `__path__` override and re-export loop from `lswitch.py`.
4. Remove or adapt tests that rely on shim behavior; add new tests asserting package-level imports.
5. Run full test-suite and CI; fix regressions.

## How to validate locally
- Run `pytest -q` and ensure all tests pass.
- Run linters/type checks if applicable.
- Run any relevant integration/smoke tests.

## Notes
- Keep changes small and well-tested; prefer multiple small PRs if the change-set is large.
- When removing a shim location, add a short note to the PR description referencing this issue.

