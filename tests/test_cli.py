"""Tests for lswitch.cli — command-line argument parsing."""

from __future__ import annotations

import types

import pytest

from lswitch.cli import main, parse_args


class TestParseArgs:
    """parse_args() returns expected Namespace for various flags."""

    def test_headless_flag(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["lswitch", "--headless"])
        args = parse_args()
        assert args.headless is True

    def test_debug_flag(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["lswitch", "--debug"])
        args = parse_args()
        assert args.debug is True

    def test_version_flag(self, monkeypatch, capsys):
        monkeypatch.setattr("sys.argv", ["lswitch", "--version"])
        with pytest.raises(SystemExit) as exc_info:
            parse_args()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "2.0.0" in captured.out

    def test_defaults_no_args(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["lswitch"])
        args = parse_args()
        assert args.headless is False
        assert args.debug is False

    def test_diagnose_wayland_flag(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["lswitch", "--diagnose-wayland"])
        args = parse_args()
        assert args.diagnose_wayland is True
        assert args.diagnose_wayland_switch_test is False

    def test_diagnose_wayland_switch_test_flag(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["lswitch", "--diagnose-wayland-switch-test"])
        args = parse_args()
        assert args.diagnose_wayland_switch_test is True


class TestMainDiagnostics:
    def test_diagnose_wayland_prints_report_and_exits_zero(self, monkeypatch, capsys):
        calls = []

        def fake_diagnostic(*, switch_test=False):
            calls.append(switch_test)
            return types.SimpleNamespace(ok=True, to_text=lambda: "[ok] probe")

        monkeypatch.setattr("sys.argv", ["lswitch", "--diagnose-wayland"])
        monkeypatch.setattr(
            "lswitch.platform.wayland_diagnostics.run_wayland_diagnostics",
            fake_diagnostic,
        )

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert calls == [False]
        assert "[ok] probe" in capsys.readouterr().out

    def test_diagnose_wayland_switch_test_passes_flag(self, monkeypatch):
        calls = []

        def fake_diagnostic(*, switch_test=False):
            calls.append(switch_test)
            return types.SimpleNamespace(ok=True, to_text=lambda: "")

        monkeypatch.setattr("sys.argv", ["lswitch", "--diagnose-wayland-switch-test"])
        monkeypatch.setattr(
            "lswitch.platform.wayland_diagnostics.run_wayland_diagnostics",
            fake_diagnostic,
        )

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert calls == [True]

    def test_diagnose_wayland_exits_nonzero_on_failure(self, monkeypatch):
        monkeypatch.setattr("sys.argv", ["lswitch", "--diagnose-wayland"])
        monkeypatch.setattr(
            "lswitch.platform.wayland_diagnostics.run_wayland_diagnostics",
            lambda *, switch_test=False: types.SimpleNamespace(ok=False, to_text=lambda: "fail"),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
