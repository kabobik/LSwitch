import pytest
from unittest.mock import MagicMock


def test_cli_main_invokes_lswitch(monkeypatch):
    # Replace LSwitch class in cli module with a fake that records run calls
    fake_app = MagicMock()
    class FakeLSwitch:
        def __init__(self, *args, **kwargs):
            self._inst = fake_app
        def run(self):
            return self._inst.run()

    monkeypatch.setattr('lswitch.cli.LSwitch', FakeLSwitch)

    # Import and run main (should create FakeLSwitch and call run)
    from lswitch.cli import main

    # Run main but it will block in run; instead, monkeypatch run to just set a flag
    fake_app.run = MagicMock()

    main()

    # Ensure our fake run was called
    assert fake_app.run.called
