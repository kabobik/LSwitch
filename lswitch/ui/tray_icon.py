"""TrayIcon — system tray icon with status indicator."""

from __future__ import annotations

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtCore import Qt

from lswitch.core.events import Event, EventType

# TODO: EventBus handlers are called synchronously from the publisher thread.
# If EventBus.publish() is called from a non-GUI thread, Qt widgets must be
# updated via QMetaObject.invokeMethod(widget, Qt.QueuedConnection, ...) to
# ensure thread-safety.  Currently the bus is synchronous and single-threaded,
# but this should be revisited if async publishing is added.


def create_simple_icon(size: int = 64) -> QIcon:
    """Create a simple keyboard icon for the system tray."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Keyboard body
    painter.setBrush(QColor(70, 130, 180))
    painter.setPen(QColor(50, 100, 150))
    painter.drawRoundedRect(4, 12, size - 8, size - 24, 6, 6)

    # Key rows (simplified)
    painter.setBrush(QColor(200, 220, 240))
    painter.setPen(Qt.NoPen)
    key_w = (size - 20) // 4
    for row in range(3):
        y = 18 + row * 10
        for col in range(4):
            x = 10 + col * (key_w + 2)
            painter.drawRect(x, y, key_w - 1, 7)

    painter.end()
    return QIcon(pixmap)


def create_adaptive_icon(layout_name: str = "", size: int = 64) -> QIcon:
    """Create an icon with layout label overlay."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Background circle
    painter.setBrush(QColor(70, 130, 180))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)

    # Layout text
    if layout_name:
        label = layout_name[:2].upper()
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPixelSize(size // 2)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, label)

    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    """System tray icon showing current layout and LSwitch status."""

    def __init__(self, event_bus=None, config=None, app: QApplication | None = None):
        icon = create_simple_icon()
        super().__init__(icon, None)
        self.event_bus = event_bus
        self.config = config
        self._app = app
        self._current_layout = ""

        # Subscribe to EventBus events
        if self.event_bus is not None:
            self.event_bus.subscribe(EventType.LAYOUT_CHANGED, self._on_layout_changed)
            self.event_bus.subscribe(EventType.CONFIG_CHANGED, self._on_config_changed)

        # Set default tooltip
        self.setToolTip("LSwitch")

    # -- public API --------------------------------------------------------

    def show(self) -> None:
        """Show the tray icon."""
        self.setVisible(True)

    def hide(self) -> None:
        """Hide the tray icon."""
        self.setVisible(False)

    def set_layout(self, layout_name: str) -> None:
        """Update tray icon to reflect current layout."""
        self._current_layout = layout_name
        label = layout_name.upper() if layout_name else ""
        self.setToolTip(f"LSwitch — {label}" if label else "LSwitch")
        self.setIcon(create_adaptive_icon(layout_name))

    def set_context_menu(self, menu) -> None:
        """Attach a context menu (QMenu or wrapper)."""
        self.setContextMenu(menu)

    def cleanup(self) -> None:
        """Unsubscribe from EventBus to prevent leaks and stale callbacks."""
        if self.event_bus is not None:
            self.event_bus.unsubscribe(EventType.LAYOUT_CHANGED, self._on_layout_changed)
            self.event_bus.unsubscribe(EventType.CONFIG_CHANGED, self._on_config_changed)

    # -- EventBus handlers -------------------------------------------------

    def _on_layout_changed(self, event: Event) -> None:
        layout = event.data if isinstance(event.data, str) else str(event.data)
        self.set_layout(layout)

    def _on_config_changed(self, event: Event) -> None:
        # Config is already updated in memory by whoever published the event;
        # no need to reload from disk.
        pass
