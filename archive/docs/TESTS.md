# Running Tests

This project contains unit and integration tests run with `pytest`.

## Headless CI / Local headless runs

To run tests in a headless environment (CI, container, or without an X server), set these environment variables:

- `LSWITCH_TEST_DISABLE_MONITORS=1` — disables native device/desktop monitoring threads used by the daemon. Useful to avoid touching evdev/X11 in CI.
- `QT_QPA_PLATFORM=offscreen` — prevents Qt from loading XCB and associated platform plugins.
- `DBUS_SESSION_BUS_ADDRESS` — unset or empty to avoid starting DBus threads.

Example:

```bash
export LSWITCH_TEST_DISABLE_MONITORS=1
export QT_QPA_PLATFORM=offscreen
unset DBUS_SESSION_BUS_ADDRESS
pytest -q
```

The repository includes a GitHub Actions workflow (`.github/workflows/python-tests.yml`) that already sets these variables for CI runs.

## Running a single test file or test

Run one test file:

```bash
pytest tests/test_config_overlay.py -q
```

Run a single test:

```bash
pytest tests/test_monitor_disable.py::test_monitors_enabled -q
```

## Notes for contributors

- Tests that require a real display or input devices are considered integration tests and should be run in a proper environment (with display server and/or hardware). Use `--run-live` to enable any gated live tests.
- See `tests/conftest.py` for configuration and fixtures used across tests.
