"""Tests for UI layer (Étape 6): TrayIcon, ContextMenu, ConfigDialog, adapters.

All PyQt5 classes are fully mocked via sys.modules replacement so tests
can run in headless CI environments without a display server.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import types
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# PyQt5 mock infrastructure — MUST happen before any UI module import
# ---------------------------------------------------------------------------

def _build_pyqt5_mocks():
    """Create a complete mock tree for PyQt5 modules."""
    pyqt5 = types.ModuleType("PyQt5")

    # --- QtCore ---
    qtcore = types.ModuleType("PyQt5.QtCore")
    qtcore.Qt = MagicMock()
    qtcore.Qt.Popup = 0x00000001
    qtcore.Qt.FramelessWindowHint = 0x00000800
    qtcore.Qt.WA_TranslucentBackground = 32
    qtcore.Qt.WA_TransparentForMouseEvents = 51
    qtcore.Qt.PointingHandCursor = 13
    qtcore.Qt.ArrowCursor = 0
    qtcore.Qt.NoFocus = 0
    qtcore.Qt.AlignCenter = 0x0084
    qtcore.Qt.NoPen = 0
    qtcore.QTimer = MagicMock()
    qtcore.QEvent = MagicMock()
    qtcore.QPoint = MagicMock(side_effect=lambda *a: MagicMock())
    qtcore.QSize = MagicMock(side_effect=lambda *a: MagicMock())
    qtcore.pyqtSignal = MagicMock(return_value=MagicMock())

    # --- QtWidgets ---
    qtwidgets = types.ModuleType("PyQt5.QtWidgets")

    class _MockQSystemTrayIcon:
        ActivationReason = MagicMock()
        def __init__(self, *a, **kw):
            self._visible = False
            self._tooltip = ""
            self._icon = None
            self._context_menu = None
        def setVisible(self, v): self._visible = v
        def isVisible(self): return self._visible
        def setToolTip(self, t): self._tooltip = t
        def toolTip(self): return self._tooltip
        def setIcon(self, icon): self._icon = icon
        def icon(self): return self._icon
        def setContextMenu(self, m): self._context_menu = m
        def contextMenu(self): return self._context_menu
        def show(self): self._visible = True
        def hide(self): self._visible = False

    class _MockQDialog:
        Accepted = 1
        Rejected = 0
        def __init__(self, *a, **kw):
            self._result = 0
        def setWindowTitle(self, t): self._title = t
        def setMinimumWidth(self, w): pass
        def show(self): pass
        def exec_(self): return self._result
        def accept(self): self._result = self.Accepted
        def reject(self): self._result = self.Rejected

    class _MockQMenu:
        def __init__(self, *a, **kw):
            self._actions = []
            self._font = None
            self._palette = MagicMock()
            self._stylesheet = ""
        def addAction(self, action):
            self._actions.append(action)
            return action
        def addSeparator(self): self._actions.append("---separator---")
        def actions(self): return [a for a in self._actions if a != "---separator---"]
        def setFont(self, f): self._font = f
        def palette(self): return self._palette
        def setPalette(self, p): self._palette = p
        def setStyleSheet(self, ss): self._stylesheet = ss
        def popup(self, pos): pass

    class _MockQAction:
        def __init__(self, *a, **kw):
            self._text = a[0] if a else ""
            self._enabled = True
            self._checkable = False
            self._checked = False
            self._icon = MagicMock()
            self.triggered = MagicMock()
            self.changed = MagicMock()
        def text(self): return self._text
        def setText(self, t): self._text = t
        def isEnabled(self): return self._enabled
        def setEnabled(self, e): self._enabled = e
        def isCheckable(self): return self._checkable
        def setCheckable(self, c): self._checkable = c
        def isChecked(self): return self._checked
        def setChecked(self, c): self._checked = c
        def icon(self): return self._icon
        def setIcon(self, i): self._icon = i
        def trigger(self): self.triggered.emit()

    class _MockQCheckBox:
        def __init__(self, *a, **kw):
            self._checked = False
        def isChecked(self): return self._checked
        def setChecked(self, c): self._checked = c
        def setFixedSize(self, *a): pass
        def setAttribute(self, *a): pass
        def setFocusPolicy(self, *a): pass
        def setStyleSheet(self, *a): pass

    class _MockQSpinBox:
        def __init__(self, *a, **kw):
            self._value = 0
            self._min = 0
            self._max = 100
        def value(self): return self._value
        def setValue(self, v): self._value = max(self._min, min(self._max, v))
        def setRange(self, lo, hi):
            self._min, self._max = lo, hi
        def setSingleStep(self, s): pass

    class _MockQDoubleSpinBox:
        def __init__(self, *a, **kw):
            self._value = 0.0
            self._min = 0.0
            self._max = 100.0
        def value(self): return self._value
        def setValue(self, v): self._value = max(self._min, min(self._max, float(v)))
        def setRange(self, lo, hi):
            self._min, self._max = float(lo), float(hi)
        def setSingleStep(self, s): pass
        def setDecimals(self, d): pass

    class _MockQWidget:
        def __init__(self, *a, **kw): pass
        def setWindowFlags(self, *a): pass
        def setAttribute(self, *a): pass
        def setStyleSheet(self, *a): pass
        def setMinimumHeight(self, *a): pass
        def setCursor(self, *a): pass
        def setFixedHeight(self, *a): pass
        def setFixedSize(self, *a): pass
        def setScaledContents(self, *a): pass
        def show(self): pass
        def hide(self): pass
        def raise_(self): pass
        def activateWindow(self): pass
        def adjustSize(self): pass
        def height(self): return 100
        def width(self): return 200
        def move(self, *a): pass
        def setPixmap(self, *a): pass

    class _MockQVBoxLayout:
        def __init__(self, *a): self._widgets = []
        def setContentsMargins(self, *a): pass
        def setSpacing(self, *a): pass
        def addWidget(self, w): self._widgets.append(w)
        def addLayout(self, l): pass
        def addStretch(self): pass

    class _MockQHBoxLayout(_MockQVBoxLayout):
        pass

    class _MockQFormLayout(_MockQVBoxLayout):
        def addRow(self, label, widget): self._widgets.append(widget)

    qtwidgets.QApplication = MagicMock()
    qtwidgets.QSystemTrayIcon = _MockQSystemTrayIcon
    qtwidgets.QDialog = _MockQDialog
    qtwidgets.QMenu = _MockQMenu
    qtwidgets.QAction = _MockQAction
    qtwidgets.QCheckBox = _MockQCheckBox
    qtwidgets.QSpinBox = _MockQSpinBox
    qtwidgets.QDoubleSpinBox = _MockQDoubleSpinBox
    qtwidgets.QWidget = _MockQWidget
    qtwidgets.QVBoxLayout = _MockQVBoxLayout
    qtwidgets.QHBoxLayout = _MockQHBoxLayout
    qtwidgets.QFormLayout = _MockQFormLayout
    qtwidgets.QLabel = MagicMock
    class _MockQPushButton:
        def __init__(self, *a, **kw):
            self.clicked = MagicMock()
        def connect(self, *a): pass
    qtwidgets.QPushButton = _MockQPushButton
    qtwidgets.QDialogButtonBox = MagicMock()
    qtwidgets.QDialogButtonBox.Ok = 0x00000400
    qtwidgets.QDialogButtonBox.Cancel = 0x00400000
    qtwidgets.QWidgetAction = MagicMock
    qtwidgets.QDesktopWidget = MagicMock
    qtwidgets.QMessageBox = MagicMock()
    qtwidgets.QInputDialog = MagicMock

    # --- QtGui ---
    qtgui = types.ModuleType("PyQt5.QtGui")
    qtgui.QIcon = MagicMock(return_value=MagicMock())
    qtgui.QPixmap = MagicMock(return_value=MagicMock())
    qtgui.QPainter = MagicMock(return_value=MagicMock())
    qtgui.QColor = MagicMock(return_value=MagicMock())
    qtgui.QPalette = MagicMock()
    qtgui.QPalette.Window = 10
    qtgui.QPalette.WindowText = 11
    qtgui.QPalette.Base = 12
    qtgui.QPalette.Text = 13
    qtgui.QPalette.Highlight = 14
    qtgui.QPalette.HighlightedText = 15
    qtgui.QFont = MagicMock
    qtgui.QCursor = MagicMock

    pyqt5.QtCore = qtcore
    pyqt5.QtWidgets = qtwidgets
    pyqt5.QtGui = qtgui

    return {
        "PyQt5": pyqt5,
        "PyQt5.QtCore": qtcore,
        "PyQt5.QtWidgets": qtwidgets,
        "PyQt5.QtGui": qtgui,
    }


# Install mocks globally so imports in UI modules resolve correctly
_qt_mocks = _build_pyqt5_mocks()
_saved_modules: dict[str, types.ModuleType | None] = {}
for mod_name, mod_obj in _qt_mocks.items():
    _saved_modules[mod_name] = sys.modules.get(mod_name)
    sys.modules[mod_name] = mod_obj

# Now safe to import UI modules
from lswitch.core.event_bus import EventBus
from lswitch.core.events import Event, EventType
from lswitch.config import ConfigManager, DEFAULT_CONFIG

from lswitch.ui.tray_icon import TrayIcon, create_simple_icon, create_adaptive_icon
from lswitch.ui.context_menu import ContextMenu
from lswitch.ui.config_dialog import ConfigDialog
from lswitch.ui.adapters import detect_desktop_environment, get_adapter
from lswitch.ui.adapters.base import BaseUIAdapter
from lswitch.ui.adapters.kde import KDEAdapter
from lswitch.ui.adapters.cinnamon import CinnamonAdapter, CustomMenu, QMenuWrapper


# ===========================================================================
# Helpers
# ===========================================================================

@pytest.fixture
def event_bus_ui():
    return EventBus()


@pytest.fixture
def config_mgr(tmp_path):
    path = str(tmp_path / "lswitch_test.json")
    return ConfigManager(config_path=path)


# ===========================================================================
# TrayIcon tests
# ===========================================================================

class TestTrayIcon:
    def test_constructor_default(self):
        tray = TrayIcon()
        assert tray.event_bus is None
        assert tray.config is None

    def test_constructor_with_event_bus(self, event_bus_ui):
        tray = TrayIcon(event_bus=event_bus_ui)
        assert tray.event_bus is event_bus_ui

    def test_constructor_with_config(self, config_mgr):
        tray = TrayIcon(config=config_mgr)
        assert tray.config is config_mgr

    def test_show_hide(self):
        tray = TrayIcon()
        tray.show()
        assert tray._visible is True
        tray.hide()
        assert tray._visible is False

    def test_set_layout_updates_tooltip(self):
        tray = TrayIcon()
        tray.set_layout("ru")
        assert "RU" in tray._tooltip

    def test_set_layout_empty(self):
        tray = TrayIcon()
        tray.set_layout("")
        assert tray._tooltip == "LSwitch"

    def test_event_bus_layout_changed(self, event_bus_ui):
        tray = TrayIcon(event_bus=event_bus_ui)
        event_bus_ui.publish(Event(type=EventType.LAYOUT_CHANGED, data="en", timestamp=time.time()))
        assert "EN" in tray._tooltip

    def test_event_bus_config_changed(self, event_bus_ui, config_mgr):
        tray = TrayIcon(event_bus=event_bus_ui, config=config_mgr)
        # Should not raise
        event_bus_ui.publish(Event(type=EventType.CONFIG_CHANGED, data=None, timestamp=time.time()))

    def test_set_context_menu(self):
        tray = TrayIcon()
        menu_mock = MagicMock()
        tray.set_context_menu(menu_mock)
        assert tray._context_menu is menu_mock


# ===========================================================================
# ContextMenu tests
# ===========================================================================

class TestContextMenu:
    def test_build_returns_menu(self, config_mgr, event_bus_ui):
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        menu = cm.build()
        assert menu is not None

    def test_build_has_actions(self, config_mgr, event_bus_ui):
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        menu = cm.build()
        # At least: title, auto_switch, user_dict, status, start, stop, restart, about, quit
        # (Plus separators)
        non_sep = [a for a in menu._actions if a != "---separator---"]
        assert len(non_sep) >= 9

    def test_toggle_auto_switch(self, config_mgr, event_bus_ui):
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        cm.build()
        initial = config_mgr.get("auto_switch")
        cm.toggle_auto_switch()
        assert config_mgr.get("auto_switch") != initial

    def test_quit_publishes_app_quit(self, config_mgr, event_bus_ui):
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        cm.build()
        received = []
        event_bus_ui.subscribe(EventType.APP_QUIT, lambda e: received.append(e))
        cm._quit()
        assert len(received) == 1
        assert received[0].type == EventType.APP_QUIT

    @patch("lswitch.ui.context_menu.subprocess")
    def test_update_status(self, mock_subprocess, config_mgr, event_bus_ui):
        mock_result = MagicMock()
        mock_result.stdout = "active\n"
        mock_subprocess.run.return_value = mock_result
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        cm.build()
        cm.update_status()
        assert "active" in cm._status_action._text

    def test_toggle_auto_switch_publishes_config_changed(self, config_mgr, event_bus_ui):
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        cm.build()
        received = []
        event_bus_ui.subscribe(EventType.CONFIG_CHANGED, lambda e: received.append(e))
        cm.toggle_auto_switch()
        assert len(received) == 1


# ===========================================================================
# ConfigDialog tests
# ===========================================================================

class TestConfigDialog:
    def test_constructor(self, config_mgr, event_bus_ui):
        dlg = ConfigDialog(config=config_mgr, event_bus=event_bus_ui)
        assert dlg.config is config_mgr
        assert dlg.event_bus is event_bus_ui

    def test_accept_saves_config(self, config_mgr, event_bus_ui):
        dlg = ConfigDialog(config=config_mgr, event_bus=event_bus_ui)
        dlg._auto_switch_cb.setChecked(True)
        dlg._threshold_spin.setValue(42)
        dlg.accept()
        assert config_mgr.get("auto_switch") is True
        assert config_mgr.get("auto_switch_threshold") == 42

    def test_accept_publishes_config_changed(self, config_mgr, event_bus_ui):
        dlg = ConfigDialog(config=config_mgr, event_bus=event_bus_ui)
        received = []
        event_bus_ui.subscribe(EventType.CONFIG_CHANGED, lambda e: received.append(e))
        dlg.accept()
        assert len(received) == 1

    def test_reject_does_not_save(self, config_mgr, event_bus_ui):
        original_auto = config_mgr.get("auto_switch")
        dlg = ConfigDialog(config=config_mgr, event_bus=event_bus_ui)
        dlg._auto_switch_cb.setChecked(not original_auto)
        dlg.reject()
        assert config_mgr.get("auto_switch") == original_auto

    def test_reset_defaults(self, config_mgr, event_bus_ui):
        config_mgr.set("auto_switch_threshold", 77)
        dlg = ConfigDialog(config=config_mgr, event_bus=event_bus_ui)
        dlg._reset_defaults()
        assert dlg._threshold_spin.value() == DEFAULT_CONFIG["auto_switch_threshold"]
        assert dlg._dct_spin.value() == DEFAULT_CONFIG["double_click_timeout"]

    def test_load_values(self, config_mgr, event_bus_ui):
        config_mgr.set("auto_switch", True)
        config_mgr.set("auto_switch_threshold", 50)
        dlg = ConfigDialog(config=config_mgr, event_bus=event_bus_ui)
        assert dlg._auto_switch_cb.isChecked() is True
        assert dlg._threshold_spin.value() == 50


# ===========================================================================
# Adapter tests
# ===========================================================================

class TestKDEAdapter:
    def test_supports_native_menu(self):
        adapter = KDEAdapter()
        assert adapter.supports_native_menu() is True

    def test_create_menu_returns_qmenu(self):
        adapter = KDEAdapter()
        menu = adapter.create_menu()
        assert menu is not None

    def test_get_theme_colors(self):
        adapter = KDEAdapter()
        colors = adapter.get_theme_colors()
        assert "bg_color" in colors
        assert "fg_color" in colors


class TestCinnamonAdapter:
    def test_supports_native_menu_false(self):
        adapter = CinnamonAdapter()
        assert adapter.supports_native_menu() is False

    def test_create_menu_returns_wrapper(self):
        adapter = CinnamonAdapter()
        menu = adapter.create_menu()
        assert isinstance(menu, QMenuWrapper)

    def test_get_theme_colors(self):
        adapter = CinnamonAdapter()
        colors = adapter.get_theme_colors()
        assert "bg_color" in colors


class TestDetectDesktop:
    def test_returns_string(self):
        result = detect_desktop_environment()
        assert isinstance(result, str)

    def test_detects_kde(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}):
            assert detect_desktop_environment() == "kde"

    def test_detects_cinnamon(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "X-Cinnamon"}):
            assert detect_desktop_environment() == "cinnamon"

    def test_unknown_fallback(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "", "DESKTOP_SESSION": ""}):
            result = detect_desktop_environment()
            assert isinstance(result, str)

    def test_get_adapter_returns_base(self):
        adapter = get_adapter()
        assert isinstance(adapter, BaseUIAdapter)


# ===========================================================================
# Icon creation tests
# ===========================================================================

class TestIconCreation:
    def test_create_simple_icon(self):
        icon = create_simple_icon()
        assert icon is not None

    def test_create_adaptive_icon(self):
        icon = create_adaptive_icon("ru")
        assert icon is not None

    def test_create_adaptive_icon_empty(self):
        icon = create_adaptive_icon("")
        assert icon is not None


# ===========================================================================
# GAP #1: TrayIcon cleanup / unsubscribe
# ===========================================================================

class TestTrayIconCleanup:
    def test_cleanup_unsubscribes_layout_changed(self, event_bus_ui):
        tray = TrayIcon(event_bus=event_bus_ui)
        # Before cleanup — event is delivered
        event_bus_ui.publish(Event(type=EventType.LAYOUT_CHANGED, data="fr", timestamp=time.time()))
        assert "FR" in tray._tooltip

        tray.cleanup()

        # After cleanup — event must NOT be delivered
        tray.set_layout("")  # reset
        event_bus_ui.publish(Event(type=EventType.LAYOUT_CHANGED, data="de", timestamp=time.time()))
        assert "DE" not in tray._tooltip

    def test_cleanup_unsubscribes_config_changed(self, event_bus_ui, config_mgr):
        tray = TrayIcon(event_bus=event_bus_ui, config=config_mgr)
        tray.cleanup()
        # Should not crash after cleanup
        event_bus_ui.publish(Event(type=EventType.CONFIG_CHANGED, data=None, timestamp=time.time()))

    def test_cleanup_idempotent_without_event_bus(self):
        tray = TrayIcon()
        tray.cleanup()  # no event_bus => must not raise


# ===========================================================================
# GAP #2: _toggle_user_dict
# ===========================================================================

class TestToggleUserDict:
    def test_toggle_user_dict_flips_config(self, config_mgr, event_bus_ui):
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        cm.build()
        initial = config_mgr.get("user_dict_enabled", False)
        cm._toggle_user_dict()
        assert config_mgr.get("user_dict_enabled") != initial

    def test_toggle_user_dict_updates_checked_state(self, config_mgr, event_bus_ui):
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        cm.build()
        cm._toggle_user_dict()
        new_val = config_mgr.get("user_dict_enabled")
        assert cm._user_dict_action.isChecked() == new_val

    def test_toggle_user_dict_publishes_event(self, config_mgr, event_bus_ui):
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        cm.build()
        received = []
        event_bus_ui.subscribe(EventType.CONFIG_CHANGED, lambda e: received.append(e))
        cm._toggle_user_dict()
        assert len(received) == 1
        assert "user_dict_enabled" in received[0].data


# ===========================================================================
# GAP #3 (BUG #3): toggle_auto_switch updates checked state
# ===========================================================================

class TestToggleAutoSwitchCheckedState:
    def test_toggle_auto_switch_updates_checked(self, config_mgr, event_bus_ui):
        cm = ContextMenu(config=config_mgr, event_bus=event_bus_ui)
        cm.build()
        cm.toggle_auto_switch()
        new_val = config_mgr.get("auto_switch")
        assert cm._auto_switch_action.isChecked() == new_val


# ===========================================================================
# GAP #5: ConfigDialog with config=None does not crash
# ===========================================================================

class TestConfigDialogNone:
    def test_config_dialog_none_config(self):
        dlg = ConfigDialog(config=None, event_bus=None)
        assert dlg.config is None
        # accept should not raise
        dlg.accept()

    def test_config_dialog_none_reject(self):
        dlg = ConfigDialog(config=None, event_bus=None)
        dlg.reject()


# ===========================================================================
# GAP #6: detect_desktop_environment for GNOME and XFCE
# ===========================================================================

class TestDetectDesktopGnomeXfce:
    def test_detects_gnome(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME", "DESKTOP_SESSION": ""}):
            assert detect_desktop_environment() == "gnome"

    def test_detects_xfce(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "XFCE", "DESKTOP_SESSION": ""}):
            assert detect_desktop_environment() == "xfce"

    def test_detects_gnome_via_session(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "", "DESKTOP_SESSION": "gnome"}):
            assert detect_desktop_environment() == "gnome"

    def test_detects_xfce_via_session(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "", "DESKTOP_SESSION": "xfce"}):
            assert detect_desktop_environment() == "xfce"


# ===========================================================================
# GAP #7: get_adapter returns KDEAdapter for KDE env
# ===========================================================================

class TestGetAdapterKDE:
    def test_get_adapter_kde(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE", "DESKTOP_SESSION": ""}):
            adapter = get_adapter()
            assert isinstance(adapter, KDEAdapter)

    def test_get_adapter_cinnamon(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "X-Cinnamon", "DESKTOP_SESSION": ""}):
            adapter = get_adapter()
            assert isinstance(adapter, CinnamonAdapter)


# ===========================================================================
# GAP #8: subprocess error in systemctl does not crash
# ===========================================================================

class TestSubprocessErrors:
    @patch("lswitch.ui.context_menu.subprocess")
    def test_get_service_status_exception(self, mock_subprocess):
        mock_subprocess.run.side_effect = OSError("systemctl not found")
        status = ContextMenu._get_service_status()
        assert status == "unknown"

    @patch("lswitch.ui.context_menu.subprocess")
    def test_systemctl_exception(self, mock_subprocess):
        mock_subprocess.run.side_effect = OSError("systemctl not found")
        # Must not raise
        ContextMenu._systemctl("start")

    @patch("lswitch.ui.context_menu.subprocess")
    def test_sighup_daemon_exception(self, mock_subprocess):
        mock_subprocess.run.side_effect = OSError("systemctl not found")
        # Must not raise
        ContextMenu._sighup_daemon()

    @patch("lswitch.ui.context_menu.subprocess")
    def test_get_service_status_timeout(self, mock_subprocess):
        mock_subprocess.run.side_effect = subprocess.TimeoutExpired(cmd="systemctl", timeout=3)
        status = ContextMenu._get_service_status()
        assert status == "unknown"
