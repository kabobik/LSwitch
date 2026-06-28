"""Tests for Wayland diagnostic probe."""

from __future__ import annotations

from lswitch.platform.wayland_diagnostics import (
    DiagnosticReport,
    run_wayland_diagnostics,
)


class _FakeDbusClient:
    def __init__(self):
        self.current = 0
        self.calls: list[tuple[str, tuple]] = []

    def call(self, method: str, *args):
        self.calls.append((method, args))
        if method == "getLayoutsList":
            return ["English (US)", "Russian"]
        if method == "getLayout":
            return self.current
        if method == "setLayout":
            self.current = args[0]
            return None
        raise AssertionError(f"Unexpected method: {method}")


def _run_fake_diagnostic(*, switch_test: bool = False):
    fake_dbus = _FakeDbusClient()

    report = run_wayland_diagnostics(
        env={
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "KDE",
        },
        switch_test=switch_test,
        qt_app_factory=lambda: object(),
        invoker_factory=lambda app: object(),
        dbus_client_factory=lambda main_thread: fake_dbus,
    )
    return report, fake_dbus


class TestDiagnosticReport:
    def test_ok_is_false_when_fail_step_exists(self):
        report = DiagnosticReport()
        report.add("ok", "first")
        report.add("fail", "second", "broken")

        assert report.ok is False
        assert "[fail] second: broken" in report.to_text()


class TestRunWaylandDiagnostics:
    def test_read_only_probe_reports_raw_and_parsed_layouts(self):
        report, fake_dbus = _run_fake_diagnostic()

        text = report.to_text()
        assert report.ok is True
        assert "[ok] session: wayland" in text
        assert "[ok] compositor: kde" in text
        assert "[ok] raw getLayoutsList:" in text
        assert "[ok] raw getLayout: 0" in text
        assert "[ok] parsed layouts: 0:en/us, 1:ru/ru" in text
        assert "[info] switch test: skipped" in text
        assert ("setLayout", (1,)) not in fake_dbus.calls

    def test_switch_test_switches_and_restores(self):
        report, fake_dbus = _run_fake_diagnostic(switch_test=True)

        text = report.to_text()
        assert report.ok is True
        assert "[ok] switch test setLayout: ru index=1" in text
        assert "[ok] switch test restore: en index=0" in text
        assert ("setLayout", (1,)) in fake_dbus.calls
        assert ("setLayout", (0,)) in fake_dbus.calls

    def test_non_wayland_or_non_kde_are_warnings_not_failures(self):
        report = run_wayland_diagnostics(
            env={
                "XDG_SESSION_TYPE": "x11",
                "XDG_CURRENT_DESKTOP": "GNOME",
            },
            qt_app_factory=lambda: object(),
            invoker_factory=lambda app: object(),
            dbus_client_factory=lambda main_thread: _FakeDbusClient(),
        )

        text = report.to_text()
        assert report.ok is True
        assert "[warn] session: x11 (expected wayland)" in text
        assert "[warn] compositor: gnome (expected kde)" in text

    def test_dbus_failure_marks_report_failed(self):
        class BrokenDbus:
            def call(self, method: str, *args):
                raise RuntimeError("no service")

        report = run_wayland_diagnostics(
            env={
                "XDG_SESSION_TYPE": "wayland",
                "XDG_CURRENT_DESKTOP": "KDE",
            },
            qt_app_factory=lambda: object(),
            invoker_factory=lambda app: object(),
            dbus_client_factory=lambda main_thread: BrokenDbus(),
        )

        assert report.ok is False
        assert "[fail] raw getLayoutsList: no service" in report.to_text()
