"""ContextMenu — right-click tray menu."""

from __future__ import annotations

import os
import signal
import subprocess
import threading

from PyQt5.QtWidgets import QMenu, QAction
from PyQt5.QtGui import QIcon

from lswitch.core.events import Event, EventType
from lswitch.i18n import t


class ContextMenu:
    """Context menu shown on tray icon right-click.

    Builds a QMenu with toggle actions, service management,
    about dialog entry, and quit action.
    """

    def __init__(self, config=None, event_bus=None, app=None):
        self.config = config
        self.event_bus = event_bus
        self._app = app  # LSwitchApp instance for debug monitor
        self._menu: QMenu | None = None
        self._status_action: QAction | None = None
        self._debug_monitor = None  # DebugMonitorWindow instance

    # -- public API --------------------------------------------------------

    def build(self) -> QMenu:
        """Build and return the context menu."""
        menu = QMenu()
        self._menu = menu

        # Title (disabled)
        title_action = QAction(t('lswitch_control'), menu)
        title_action.setEnabled(False)
        menu.addAction(title_action)
        menu.addSeparator()

        # Auto-switch toggle
        self._auto_switch_action = QAction(t('auto_switch'), menu)
        self._auto_switch_action.setCheckable(True)
        auto_val = self.config.get("auto_switch", False) if self.config else False
        self._auto_switch_action.setChecked(auto_val)
        self._auto_switch_action.triggered.connect(self.toggle_auto_switch)
        menu.addAction(self._auto_switch_action)

        # User dictionary toggle
        self._user_dict_action = QAction(t('self_learning_dict'), menu)
        self._user_dict_action.setCheckable(True)
        ud_val = self.config.get("user_dict_enabled", False) if self.config else False
        self._user_dict_action.setChecked(ud_val)
        self._user_dict_action.triggered.connect(self._toggle_user_dict)
        menu.addAction(self._user_dict_action)

        menu.addSeparator()

        # Service status (disabled, informational)
        self._status_action = QAction(f"{t('status')}: {t('status_unknown')}", menu)
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)

        # Service control actions
        start_action = QAction(t('start'), menu)
        start_action.triggered.connect(lambda: threading.Thread(target=self._systemctl, args=("start",), daemon=True).start())
        menu.addAction(start_action)

        stop_action = QAction(t('stop'), menu)
        stop_action.triggered.connect(lambda: threading.Thread(target=self._systemctl, args=("stop",), daemon=True).start())
        menu.addAction(stop_action)

        restart_action = QAction(t('restart'), menu)
        restart_action.triggered.connect(lambda: threading.Thread(target=self._systemctl, args=("restart",), daemon=True).start())
        menu.addAction(restart_action)

        menu.addSeparator()

        # Debug Monitor (only when debug mode is enabled)
        if self.config and self.config.get("debug", False):
            debug_action = QAction("Debug Monitor", menu)
            debug_action.triggered.connect(self._show_debug_monitor)
            menu.addAction(debug_action)
            menu.addSeparator()

        # About
        about_action = QAction(t('about'), menu)
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)

        # Quit
        quit_action = QAction(t('quit_panel'), menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        # Initial status update
        self.update_status()

        return menu

    def update_status(self) -> None:
        """Refresh the service status label."""
        if self._status_action is None:
            return
        status = self._get_service_status()
        self._status_action.setText(f"{t('status')}: {status}")

    def toggle_auto_switch(self) -> None:
        """Toggle auto_switch config, save, and SIGHUP daemon."""
        if self.config is None:
            return
        current = self.config.get("auto_switch", False)
        new_val = not current
        self.config.set("auto_switch", new_val)
        self.config.save()
        if hasattr(self, '_auto_switch_action'):
            self._auto_switch_action.setChecked(new_val)
        threading.Thread(target=self._sighup_daemon, daemon=True).start()

        if self.event_bus is not None:
            import time
            self.event_bus.publish(
                Event(type=EventType.CONFIG_CHANGED, data={"auto_switch": new_val}, timestamp=time.time())
            )

    # -- internals ---------------------------------------------------------

    def _toggle_user_dict(self) -> None:
        if self.config is None:
            return
        current = self.config.get("user_dict_enabled", False)
        new_val = not current
        self.config.set("user_dict_enabled", new_val)
        self.config.save()
        if hasattr(self, '_user_dict_action'):
            self._user_dict_action.setChecked(new_val)
        threading.Thread(target=self._sighup_daemon, daemon=True).start()

        if self.event_bus is not None:
            import time
            self.event_bus.publish(
                Event(type=EventType.CONFIG_CHANGED, data={"user_dict_enabled": new_val}, timestamp=time.time())
            )

    def update_status_async(self) -> None:
        """Refresh service status in a background thread to avoid blocking the GUI."""
        def _worker():
            status = self._get_service_status()
            if self._status_action is not None:
                self._status_action.setText(f"{t('status')}: {status}")
        threading.Thread(target=_worker, daemon=True).start()

    @staticmethod
    def _get_service_status() -> str:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "lswitch.service"],
                capture_output=True, text=True, timeout=3,
            )
            return result.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    @staticmethod
    def _systemctl(action: str) -> None:
        try:
            subprocess.run(
                ["systemctl", "--user", action, "lswitch.service"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            pass

    @staticmethod
    def _sighup_daemon() -> None:
        """Send SIGHUP to the running lswitch daemon to reload config."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "show", "-p", "MainPID", "lswitch.service"],
                capture_output=True, text=True, timeout=3,
            )
            for line in result.stdout.splitlines():
                if line.startswith("MainPID="):
                    pid = int(line.split("=")[1])
                    if pid > 0:
                        os.kill(pid, signal.SIGHUP)
        except Exception:
            pass

    @staticmethod
    def _show_about() -> None:
        try:
            from PyQt5.QtWidgets import QMessageBox
            from lswitch import __version__
            QMessageBox.about(None, t('about_title', version=__version__), t('about_description'))
        except Exception:
            pass

    def _show_debug_monitor(self) -> None:
        """Open or raise the Debug Monitor window."""
        try:
            from lswitch.ui.debug_monitor import DebugMonitorWindow

            if self._debug_monitor is None or not self._debug_monitor.isVisible():
                self._debug_monitor = DebugMonitorWindow(
                    app=self._app,
                    event_bus=self.event_bus,
                )
            self._debug_monitor.show()
            self._debug_monitor.raise_()
            self._debug_monitor.activateWindow()
        except Exception:
            pass

    def _quit(self) -> None:
        if self.event_bus is not None:
            import time
            self.event_bus.publish(
                Event(type=EventType.APP_QUIT, data=None, timestamp=time.time())
            )
