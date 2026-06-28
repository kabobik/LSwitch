"""Tests for platform session detection and adapter factory boundaries."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lswitch.platform.platform_factory import (
    PlatformAdapters,
    PlatformRuntimePlan,
    create_platform_adapters,
    create_runtime_plan,
    create_wayland_platform_adapters,
    create_x11_platform_adapters,
    detect_compositor,
    detect_session_type,
)
from lswitch.platform.main_thread import DirectMainThreadInvoker
from lswitch.platform.selection_adapter import X11SelectionAdapter
from lswitch.platform.subprocess_impl import SubprocessSystemAdapter
from lswitch.platform.wayland import (
    WaylandBackendNotImplementedError,
    WaylandLayoutAdapter,
    WaylandSelectionAdapter,
    WaylandSystemAdapter,
)
from lswitch.platform.xkb_adapter import X11XKBAdapter


class TestDetectSessionType:
    def test_explicit_wayland(self):
        assert detect_session_type({"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}) == "wayland"

    def test_explicit_x11(self):
        assert detect_session_type({"XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": "wayland-0"}) == "x11"

    def test_wayland_display_fallback(self):
        assert detect_session_type({"WAYLAND_DISPLAY": "wayland-0"}) == "wayland"

    def test_display_fallback(self):
        assert detect_session_type({"DISPLAY": ":0"}) == "x11"

    def test_unknown(self):
        assert detect_session_type({}) == "unknown"


class TestDetectCompositor:
    def test_hyprland_env_wins(self):
        assert detect_compositor({"HYPRLAND_INSTANCE_SIGNATURE": "abc"}) == "hyprland"

    def test_sway_env(self):
        assert detect_compositor({"SWAYSOCK": "/tmp/sway.sock"}) == "sway"

    def test_kde_desktop(self):
        assert detect_compositor({"XDG_CURRENT_DESKTOP": "KDE"}) == "kde"

    def test_gnome_desktop(self):
        assert detect_compositor({"XDG_CURRENT_DESKTOP": "GNOME"}) == "gnome"

    def test_unknown(self):
        assert detect_compositor({}) == "unknown"


class TestCreateRuntimePlan:
    def test_x11_headless_does_not_need_qt_loop(self):
        plan = create_runtime_plan(headless=True, env={"XDG_SESSION_TYPE": "x11"})

        assert isinstance(plan, PlatformRuntimePlan)
        assert plan.uses_qt_event_loop is False
        assert plan.requires_qt_before_platform is False
        assert plan.show_tray is False

    def test_x11_gui_uses_qt_loop_for_tray(self):
        plan = create_runtime_plan(headless=False, env={"XDG_SESSION_TYPE": "x11"})

        assert plan.uses_qt_event_loop is True
        assert plan.requires_qt_before_platform is False
        assert plan.show_tray is True

    def test_wayland_headless_requires_qt_before_platform(self):
        plan = create_runtime_plan(headless=True, env={"XDG_SESSION_TYPE": "wayland"})

        assert plan.uses_qt_event_loop is True
        assert plan.requires_qt_before_platform is True
        assert plan.show_tray is False


class TestCreatePlatformAdapters:
    def test_wayland_session_returns_skeleton_adapters(self):
        fake_vk = MagicMock()
        fake_layout_backend = MagicMock()
        main_thread = DirectMainThreadInvoker()
        with patch("lswitch.platform.platform_factory.VirtualKeyboard", return_value=fake_vk):
            adapters = create_platform_adapters(
                debug=True,
                main_thread=main_thread,
                layout_backend=fake_layout_backend,
                env={
                    "XDG_SESSION_TYPE": "wayland",
                    "XDG_CURRENT_DESKTOP": "KDE",
                },
            )

        assert isinstance(adapters, PlatformAdapters)
        assert adapters.session_type == "wayland"
        assert adapters.compositor == "kde"
        assert isinstance(adapters.system, WaylandSystemAdapter)
        assert isinstance(adapters.xkb, WaylandLayoutAdapter)
        assert isinstance(adapters.selection, WaylandSelectionAdapter)
        assert adapters.virtual_kb is fake_vk
        assert adapters.selection_polling_enabled is False
        assert adapters.main_thread is main_thread
        assert adapters.selection_mouse_release_tracking_enabled is False
        fake_layout_backend.validate.assert_called_once()

    def test_unknown_session_fails_clearly(self):
        with patch("lswitch.platform.platform_factory.detect_session_type", return_value="unknown"):
            with pytest.raises(RuntimeError, match="requires an active"):
                create_platform_adapters()

    def test_wayland_requires_main_thread_invoker(self):
        with pytest.raises(RuntimeError, match="main-thread invoker"):
            create_platform_adapters(
                debug=True,
                env={"XDG_SESSION_TYPE": "wayland"},
            )

    def test_create_x11_platform_adapters_wires_concrete_types(self):
        fake_vk = MagicMock()
        with patch("lswitch.platform.platform_factory.VirtualKeyboard", return_value=fake_vk):
            with patch.object(X11XKBAdapter, "__init__", return_value=None):
                adapters = create_x11_platform_adapters(debug=True, compositor="kde")

        assert isinstance(adapters, PlatformAdapters)
        assert adapters.session_type == "x11"
        assert adapters.compositor == "kde"
        assert isinstance(adapters.system, SubprocessSystemAdapter)
        assert isinstance(adapters.xkb, X11XKBAdapter)
        assert isinstance(adapters.selection, X11SelectionAdapter)
        assert adapters.virtual_kb is fake_vk
        assert adapters.selection_polling_enabled is True
        assert adapters.selection_mouse_release_tracking_enabled is True

    def test_create_wayland_platform_adapters_fail_fast_for_layout_and_subprocess(self):
        fake_vk = MagicMock()
        main_thread = DirectMainThreadInvoker()
        with patch("lswitch.platform.platform_factory.VirtualKeyboard", return_value=fake_vk):
            adapters = create_wayland_platform_adapters(
                debug=True,
                compositor="unknown",
                main_thread=main_thread,
            )

        with pytest.raises(WaylandBackendNotImplementedError, match="switch_layout"):
            adapters.xkb.switch_layout()
        with pytest.raises(WaylandBackendNotImplementedError, match="run_command"):
            adapters.system.run_command(["true"])
