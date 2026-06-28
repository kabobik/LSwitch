"""Tests for platform session detection and adapter factory boundaries."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lswitch.platform.platform_factory import (
    PlatformAdapters,
    create_platform_adapters,
    create_x11_platform_adapters,
    detect_compositor,
    detect_session_type,
)
from lswitch.platform.selection_adapter import X11SelectionAdapter
from lswitch.platform.subprocess_impl import SubprocessSystemAdapter
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


class TestCreatePlatformAdapters:
    def test_wayland_fails_at_factory_boundary(self):
        with patch("lswitch.platform.platform_factory.detect_session_type", return_value="wayland"):
            with pytest.raises(RuntimeError, match="Wayland session detected"):
                create_platform_adapters()

    def test_unknown_session_fails_clearly(self):
        with patch("lswitch.platform.platform_factory.detect_session_type", return_value="unknown"):
            with pytest.raises(RuntimeError, match="requires an active"):
                create_platform_adapters()

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
