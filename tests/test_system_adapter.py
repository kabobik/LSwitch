"""Tests for SubprocessSystemAdapter and MockSystemAdapter."""

from __future__ import annotations

import pytest

from lswitch.platform.subprocess_impl import SubprocessSystemAdapter
from lswitch.platform.system_adapter import CommandResult, ISystemAdapter

# Re-use mock from conftest
from tests.conftest import MockSystemAdapter


# ---------------------------------------------------------------------------
# SubprocessSystemAdapter tests
# ---------------------------------------------------------------------------

class TestSubprocessSystemAdapter:
    def test_run_command_success(self):
        """echo hello should return 'hello\\n' with returncode 0."""
        adapter = SubprocessSystemAdapter()
        result = adapter.run_command(["echo", "hello"])
        assert isinstance(result, CommandResult)
        assert result.returncode == 0
        assert result.stdout.strip() == "hello"

    def test_run_command_failure(self):
        """Running a nonexistent command returns nonzero."""
        adapter = SubprocessSystemAdapter()
        result = adapter.run_command(["false"])
        assert result.returncode != 0

    def test_run_command_timeout(self):
        """Extremely small timeout should trigger timeout handling."""
        adapter = SubprocessSystemAdapter()
        # sleep 10 with 0.01s timeout → should timeout
        result = adapter.run_command(["sleep", "10"], timeout=0.01)
        assert result.returncode == -1
        assert "timeout" in result.stderr.lower()

    def test_run_command_invalid_binary(self):
        """Nonexistent binary returns -1 returncode (graceful error)."""
        adapter = SubprocessSystemAdapter()
        result = adapter.run_command(["__nonexistent_binary_12345__"])
        assert result.returncode == -1

    def test_xdotool_key_no_crash(self):
        """xdotool_key should not raise even if xdotool is not installed."""
        adapter = SubprocessSystemAdapter()
        # Should not raise — failure is silently handled
        adapter.xdotool_key("ctrl+a", timeout=0.1)

    def test_get_clipboard_returns_string(self):
        """get_clipboard should always return a string (even if empty)."""
        adapter = SubprocessSystemAdapter()
        result = adapter.get_clipboard(selection="primary")
        assert isinstance(result, str)

    def test_set_clipboard_no_crash(self):
        """set_clipboard should not raise."""
        adapter = SubprocessSystemAdapter()
        adapter.set_clipboard("test", selection="clipboard")

    def test_implements_interface(self):
        adapter = SubprocessSystemAdapter()
        assert isinstance(adapter, ISystemAdapter)


# ---------------------------------------------------------------------------
# MockSystemAdapter tests
# ---------------------------------------------------------------------------

class TestMockSystemAdapter:
    def test_implements_interface(self, mock_system: MockSystemAdapter):
        assert isinstance(mock_system, ISystemAdapter)

    def test_run_command_returns_result(self, mock_system: MockSystemAdapter):
        result = mock_system.run_command(["ls"])
        assert isinstance(result, CommandResult)
        assert result.returncode == 0

    def test_xdotool_key_noop(self, mock_system: MockSystemAdapter):
        mock_system.xdotool_key("ctrl+a")  # no crash

    def test_get_clipboard_empty(self, mock_system: MockSystemAdapter):
        result = mock_system.get_clipboard()
        assert result == ""

    def test_set_clipboard_noop(self, mock_system: MockSystemAdapter):
        mock_system.set_clipboard("test")  # no crash
