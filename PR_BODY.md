Title: Stabilize headless test runs: add monitor-disable flag and offscreen Qt

Summary

This patchset stabilizes running the test suite in headless CI environments by:

- Adding support for `LSWITCH_TEST_DISABLE_MONITORS` which, when set to `1`, prevents LSwitch from starting native monitoring threads that touch evdev/X11 in tests.
- Ensuring tests set `QT_QPA_PLATFORM=offscreen` and remove `DBUS_SESSION_BUS_ADDRESS` in `tests/conftest.py` to avoid loading XCB/DBus platform plugins in headless environments.
- Adding unit tests: `tests/test_monitor_disable.py` to verify both disabled and enabled monitor behavior.
- Fixing tests that created a `QApplication` at import time (`tests/test_adapters.py`) so Pytest does not load Qt plugins during import.
- Updating `docs/CHANGELOG.md` with the change and adding tests for CI stability.

Why

Running the full test suite in CI previously caused intermittent segmentation faults due to PyQt loading platform plugins and native threads running in parallel with the test harness. These fixes make the suite stable in headless CI and make it safe to run the entire test suite in jobs without an X server.

Notes for reviewers

- CI should set `LSWITCH_TEST_DISABLE_MONITORS=1` for headless runners (or use Xvfb) and keep `QT_QPA_PLATFORM=offscreen` active during tests.
- The changes are backward compatible — production runtime is unaffected unless the environment variable is set.
