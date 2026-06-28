"""Read-only diagnostics for Wayland/KDE platform integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping
from xml.etree import ElementTree

from lswitch.platform.platform_factory import detect_compositor, detect_session_type
from lswitch.platform.wayland import (
    KdeKeyboardDbusClient,
    KdeLayoutBackend,
)


@dataclass(frozen=True)
class DiagnosticStep:
    status: str
    label: str
    detail: str = ""

    def format(self) -> str:
        suffix = f": {self.detail}" if self.detail else ""
        return f"[{self.status}] {self.label}{suffix}"


@dataclass
class DiagnosticReport:
    steps: list[DiagnosticStep] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(step.status == "fail" for step in self.steps)

    def add(self, status: str, label: str, detail: str = "") -> None:
        self.steps.append(DiagnosticStep(status=status, label=label, detail=detail))

    def to_text(self) -> str:
        return "\n".join(step.format() for step in self.steps)


def run_wayland_diagnostics(
    *,
    env: Mapping[str, str] | None = None,
    switch_test: bool = False,
    dbus_client_factory: Callable[[object], object] | None = None,
    qt_app_factory: Callable[[], object] | None = None,
    invoker_factory: Callable[[object], object] | None = None,
) -> DiagnosticReport:
    """Probe Wayland/KDE runtime state without starting the daemon."""
    report = DiagnosticReport()

    session_type = detect_session_type(env)
    compositor = detect_compositor(env)
    _add_expected(report, "session", session_type, expected="wayland")
    _add_expected(report, "compositor", compositor, expected="kde")

    if dbus_client_factory is None:
        try:
            import PyQt6.QtDBus  # noqa: F401
            report.add("ok", "PyQt6.QtDBus", "import ok")
        except Exception as exc:
            report.add("fail", "PyQt6.QtDBus", str(exc))
            return report
    else:
        report.add("ok", "PyQt6.QtDBus", "skipped; injected D-Bus client")

    try:
        if qt_app_factory is None:
            from lswitch.ui.qt_bridge import ensure_qt_core_application
            qt_app_factory = lambda: ensure_qt_core_application(["lswitch-diagnose"])
        qt_app = qt_app_factory()
        report.add("ok", "Qt core application", type(qt_app).__name__)
    except Exception as exc:
        report.add("fail", "Qt core application", str(exc))
        return report

    try:
        if invoker_factory is None:
            from lswitch.ui.qt_bridge import QtMainThreadInvoker
            invoker_factory = QtMainThreadInvoker
        main_thread = invoker_factory(qt_app)
        report.add("ok", "Qt main-thread bridge", type(main_thread).__name__)
    except Exception as exc:
        report.add("fail", "Qt main-thread bridge", str(exc))
        return report

    try:
        dbus_client = (
            dbus_client_factory(main_thread)
            if dbus_client_factory is not None
            else KdeKeyboardDbusClient(main_thread)
        )
        report.add(
            "ok",
            "KDE D-Bus target",
            (
                f"{KdeKeyboardDbusClient.SERVICE} "
                f"{KdeKeyboardDbusClient.PATH} "
                f"{KdeKeyboardDbusClient.INTERFACE}"
            ),
        )
    except Exception as exc:
        report.add("fail", "KDE D-Bus client", str(exc))
        return report

    _add_dbus_introspection(report, dbus_client)

    try:
        raw_layouts = dbus_client.call("getLayoutsList")
        report.add("ok", "raw getLayoutsList", repr(raw_layouts))
    except Exception as exc:
        report.add("fail", "raw getLayoutsList", str(exc))
        return report

    try:
        raw_current = dbus_client.call("getLayout")
        report.add("ok", "raw getLayout", repr(raw_current))
    except Exception as exc:
        report.add("fail", "raw getLayout", str(exc))
        return report

    try:
        backend = KdeLayoutBackend(dbus_client)
        layouts = backend.get_layouts()
        current = backend.get_current_layout()
        report.add("ok", "parsed layouts", _format_layouts(layouts))
        report.add(
            "ok",
            "parsed current layout",
            f"{current.name} index={current.index} xkb={current.xkb_name}",
        )
    except Exception as exc:
        report.add("fail", "parsed KDE layouts", str(exc))
        return report

    if switch_test:
        _run_switch_test(report, backend, current)
    else:
        report.add("info", "switch test", "skipped; pass --diagnose-wayland-switch-test")

    return report


def _add_expected(
    report: DiagnosticReport,
    label: str,
    value: str,
    *,
    expected: str,
) -> None:
    if value == expected:
        report.add("ok", label, value)
    else:
        report.add("warn", label, f"{value} (expected {expected})")


def _format_layouts(layouts) -> str:
    return ", ".join(
        f"{layout.index}:{layout.name}/{layout.xkb_name}" for layout in layouts
    )


def _add_dbus_introspection(report: DiagnosticReport, dbus_client) -> None:
    introspect = getattr(dbus_client, "introspect", None)
    if introspect is None:
        report.add("warn", "D-Bus introspection", "not available")
        return

    try:
        xml = introspect()
        methods = _parse_dbus_methods(xml)
        detail = ", ".join(methods) if methods else "no methods found"
        report.add("ok", "D-Bus methods", detail)
    except Exception as exc:
        report.add("warn", "D-Bus introspection", str(exc))


def _parse_dbus_methods(xml: str) -> list[str]:
    root = ElementTree.fromstring(xml)
    methods = {
        _format_dbus_method(method)
        for method in root.findall(".//method")
        if method.attrib.get("name")
    }
    return sorted(methods)


def _format_dbus_method(method: ElementTree.Element) -> str:
    name = method.attrib["name"]
    input_signature = _method_arg_signature(method, direction="in")
    output_signature = _method_arg_signature(method, direction="out")
    formatted = f"{name}({input_signature})"
    if output_signature:
        formatted += f"->{output_signature}"
    return formatted


def _method_arg_signature(method: ElementTree.Element, *, direction: str) -> str:
    parts = []
    for arg in method.findall("arg"):
        arg_direction = arg.attrib.get("direction", "in")
        if arg_direction != direction:
            continue
        arg_type = arg.attrib.get("type", "")
        if arg_type:
            parts.append(arg_type)
    return "".join(parts)


def _run_switch_test(report: DiagnosticReport, backend: KdeLayoutBackend, original) -> None:
    layouts = backend.get_layouts()
    if len(layouts) < 2:
        report.add("warn", "switch test", "skipped; only one layout configured")
        return

    target = layouts[(original.index + 1) % len(layouts)]
    try:
        switched = backend.switch_layout(target=target)
        report.add(
            "ok",
            "switch test switch",
            f"{switched.name} index={switched.index}",
        )
        restored = backend.switch_layout(target=original)
        report.add(
            "ok",
            "switch test restore",
            f"{restored.name} index={restored.index}",
        )
    except Exception as exc:
        report.add("fail", "switch test", str(exc))
