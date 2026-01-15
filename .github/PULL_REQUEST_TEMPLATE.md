## Summary

Reference issue: #<issue-number> (Refactor: remove temporary compatibility shim)

Describe what this PR changes and why. Be explicit about **which temporary
compatibility hacks are removed or modified** (e.g. `lswitch.py` shim, re-export
loop, `__path__` override).

## Checklist
- [ ] Linked to the issue tracking the cleanup
- [ ] Removed shim code (list files changed below)
- [ ] Updated tests (removed or migrated tests that relied on shim internals)
- [ ] Updated docs / CHANGELOG
- [ ] All unit tests pass locally (`pytest -q`)
- [ ] CI is green

## Files changed (examples)
- `lswitch.py` — remove `<details>`
- `tests/test_shim_documentation.py` — update/remove if needed
- Any modules where `TODO: remove` marker was deleted

## Validation steps
1. Run `pytest -q` to ensure all tests pass.
2. Verify no references to the shim markers remain: `git grep -n "TODO: remove"`.
3. Double-check CI pipeline for platform-specific failures.

## Notes for reviewers
- Prefer small focused PRs: separate the removal of `__path__` from large call-site changes.
- If a test was removed because it asserted shim internals, add a short description of why
  in the PR description and link to a follow-up task if needed.

