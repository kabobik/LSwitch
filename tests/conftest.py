import signal
import os
import sys
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--keyboard-watchdog",
        action="store",
        default="10",
        help="Timeout in seconds after which watchdog will attempt to release virtual keyboard and fail the test"
    )
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Enable interactive live tests (skipped by default)."
    )
    parser.addoption(
        "--live-timeout",
        action="store",
        default="20",
        help="Inactivity timeout (seconds) for live interactive tests."
    )


@pytest.fixture(autouse=True)
def mock_uinput(monkeypatch):
    """Replace real evdev.UInput with a test Dummy to avoid grabbing /dev/uinput in tests.

    This fixture is autouse so tests that forgot to mock UInput won't hang the CI or the developer machine.
    It also performs a best-effort cleanup after the test by calling force_release_virtual_keyboards().
    """
    import sys
    import os

    class DummyUInput:
        def __init__(self, *args, **kwargs):
            # Simple diagnostic to help debugging hangs — will show up with -s
            print(f"[test] DummyUInput() created pid={os.getpid()}", file=sys.stderr)
        def write(self, *a, **k):
            pass
        def syn(self):
            pass
        def close(self):
            # mimic real UInput close
            pass

    monkeypatch.setattr('evdev.UInput', DummyUInput)

    yield

    # Best-effort cleanup in case test left something open
    try:
        import lswitch as ls_mod
        ls_mod.force_release_virtual_keyboards()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def keyboard_watchdog(request):
    timeout = int(request.config.getoption('--keyboard-watchdog') or 10)

    def handler(signum, frame):
        # Emergency cleanup: try to release virtual keyboards owned by this process
        try:
            import lswitch as ls_mod
            touched = ls_mod.force_release_virtual_keyboards()
            print(f"⚠️ Keyboard watchdog triggered: closed {touched} virtual keyboards; aborting test to free input devices.", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ Keyboard watchdog cleanup failed: {e}", file=sys.stderr)
        # Ensure the process exits to free grabbed devices — use _exit to avoid cleanup deadlocks
        os._exit(70)

    old_handler = signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
