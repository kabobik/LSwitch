"""ContextMenu — right-click tray menu."""

from __future__ import annotations

from PyQt6.QtWidgets import QMenu, QMessageBox
from PyQt6.QtGui import QAction, QIcon

from lswitch.core.events import Event, EventType
from lswitch.i18n import t
from lswitch.runtime_config import RuntimeConfigController


class ContextMenu:
    """Context menu shown on tray icon right-click.

    Builds a QMenu with toggle actions, process status, about dialog entry,
    and quit action.
    """

    def __init__(
        self,
        config=None,
        event_bus=None,
        app=None,
        config_controller=None,
    ):
        self.config = config
        self.event_bus = event_bus
        self._app = app  # LSwitchApp instance for debug monitor
        self.config_controller = config_controller
        if self.config_controller is None and self.config is not None:
            self.config_controller = RuntimeConfigController(
                config=self.config,
                event_bus=self.event_bus,
            )
        self._menu: QMenu | None = None
        self._status_action: QAction | None = None
        self._debug_monitor = None  # DebugMonitorWindow instance
        self._settings_dialog = None
        self._subscribed = False

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

        self._settings_action = QAction(t("settings_menu"), menu)
        self._settings_action.triggered.connect(self._show_settings)
        menu.addAction(self._settings_action)

        menu.addSeparator()

        # Status (informational — shows this process is running)
        self._status_action = QAction(f"{t('status')}: active", menu)
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)

        menu.addSeparator()

        # Created once; visibility follows effective live debug state.
        self._debug_action = QAction(t("debug_monitor"), menu)
        self._debug_action.triggered.connect(self._show_debug_monitor)
        menu.addAction(self._debug_action)
        self._set_debug_action_visible(self._effective_debug())
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
        self._subscribe()

        return menu

    def update_status(self) -> None:
        """Refresh the status label (always active — we ARE the process)."""
        if self._status_action is None:
            return
        self._status_action.setText(f"{t('status')}: active")

    def toggle_auto_switch(self) -> None:
        """Toggle auto_switch config, save, and notify via event bus."""
        if self.config is None:
            return
        current = self.config.get("auto_switch", False)
        new_val = not current
        if not self._apply_value("auto_switch", new_val):
            if hasattr(self, '_auto_switch_action'):
                self._auto_switch_action.setChecked(current)
            return
        if hasattr(self, '_auto_switch_action'):
            self._auto_switch_action.setChecked(new_val)

    # -- internals ---------------------------------------------------------

    def _toggle_user_dict(self) -> None:
        if self.config is None:
            return
        current = self.config.get("user_dict_enabled", False)
        new_val = not current
        if not self._apply_value("user_dict_enabled", new_val):
            if hasattr(self, '_user_dict_action'):
                self._user_dict_action.setChecked(current)
            return
        if hasattr(self, '_user_dict_action'):
            self._user_dict_action.setChecked(new_val)

    def _apply_value(self, key: str, value) -> bool:
        if self.config is None or self.config_controller is None:
            return False
        candidate = self.config.get_all()
        candidate[key] = value
        result = self.config_controller.apply(candidate, source="tray")
        if not result.ok:
            QMessageBox.critical(
                None,
                t("settings_error_title"),
                result.error or t("settings_unknown_error"),
            )
        return result.ok

    def _show_settings(self) -> None:
        """Create one modeless settings dialog and raise it on later calls."""
        from lswitch.ui.config_dialog import ConfigDialog

        if self._settings_dialog is None:
            self._settings_dialog = ConfigDialog(
                config=self.config,
                event_bus=self.event_bus,
                config_controller=self.config_controller,
                app=self._app,
            )
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _subscribe(self) -> None:
        if self.event_bus is not None and not self._subscribed:
            self.event_bus.subscribe(EventType.CONFIG_CHANGED, self._on_config_changed)
            self._subscribed = True

    def cleanup(self) -> None:
        if self.event_bus is not None and self._subscribed:
            self.event_bus.unsubscribe(EventType.CONFIG_CHANGED, self._on_config_changed)
            self._subscribed = False
        if self._settings_dialog is not None:
            self._settings_dialog.cleanup()

    def _on_config_changed(self, event) -> None:
        if self.config is None:
            return
        if hasattr(self, "_auto_switch_action"):
            self._auto_switch_action.setChecked(
                self.config.get("auto_switch", False)
            )
        if hasattr(self, "_user_dict_action"):
            self._user_dict_action.setChecked(
                self.config.get("user_dict_enabled", False)
            )
        if hasattr(self, "_debug_action"):
            self._set_debug_action_visible(self._effective_debug())

    def _effective_debug(self) -> bool:
        if self._app is not None:
            return bool(getattr(self._app, "debug", False))
        return bool(self.config and self.config.get("debug", False))

    def _set_debug_action_visible(self, visible: bool) -> None:
        if hasattr(self, "_debug_action"):
            self._debug_action.setVisible(bool(visible))

    @staticmethod
    def _show_about() -> None:
        try:
            from PyQt6.QtWidgets import QMessageBox
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
