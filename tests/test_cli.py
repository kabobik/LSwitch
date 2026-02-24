"""Tests for lswitch.cli — command-line argument parsing."""

from __future__ import annotations

import pytest

from lswitch.cli import parse_args


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
