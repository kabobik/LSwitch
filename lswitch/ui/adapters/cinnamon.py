"""CinnamonAdapter — Cinnamon-specific tray/menu with custom widgets."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QDesktopWidget,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt5.QtGui import QIcon

from lswitch.ui.adapters.base import BaseUIAdapter


# ---------------------------------------------------------------------------
# Custom widget menu items (for Cinnamon, where native QMenu theming fails)
# ---------------------------------------------------------------------------

class CustomMenuItem(QWidget):
    """Single menu item with hover effect and optional checkbox."""

    clicked = pyqtSignal()

    def __init__(
        self,
        text: str,
        icon: QIcon | None = None,
        bg_color: tuple = (46, 46, 51),
        fg_color: tuple = (255, 255, 255),
        checkable: bool = False,
    ):
        super().__init__()
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.hover_color = tuple(min(255, c + 20) for c in bg_color)
        self._enabled = True
        self.checkable = checkable
        self.checkbox: QCheckBox | None = None

        self.setMinimumHeight(28)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        if checkable:
            self.checkbox = QCheckBox()
            self.checkbox.setFixedSize(16, 16)
            self.checkbox.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.checkbox.setFocusPolicy(Qt.NoFocus)
            layout.addWidget(self.checkbox)
            self.icon_label = None
        else:
            self.icon_label = QLabel()
            self.icon_label.setFixedSize(16, 16)
            self.icon_label.setScaledContents(True)
            if icon and not icon.isNull():
                pixmap = icon.pixmap(QSize(16, 16))
                self.icon_label.setPixmap(pixmap)
            layout.addWidget(self.icon_label)

        self.label = QLabel(text)
        self.label.setStyleSheet(
            f"color: rgb({fg_color[0]},{fg_color[1]},{fg_color[2]}); "
            "background: transparent; font-size: 14px;"
        )
        layout.addWidget(self.label)
        layout.addStretch()

        self._update_style(False)

    # -- public helpers ----------------------------------------------------

    def setChecked(self, checked: bool) -> None:
        if self.checkbox:
            self.checkbox.setChecked(checked)

    def isChecked(self) -> bool:
        return self.checkbox.isChecked() if self.checkbox else False

    def setText(self, text: str) -> None:
        self.label.setText(text)

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self._update_style(False)

    # -- events ------------------------------------------------------------

    def enterEvent(self, event):
        if self._enabled:
            self._update_style(True)

    def leaveEvent(self, event):
        self._update_style(False)

    def mousePressEvent(self, event):
        if self._enabled:
            self.clicked.emit()

    # -- private -----------------------------------------------------------

    def _update_style(self, hover: bool) -> None:
        color = self.hover_color if (hover and self._enabled) else self.bg_color
        self.setStyleSheet(
            f"background-color: rgb({color[0]},{color[1]},{color[2]}); border: none;"
        )


class CustomMenuSeparator(QWidget):
    """Horizontal separator line inside CustomMenu."""

    def __init__(self, color: tuple = (60, 60, 65)):
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet(
            f"background-color: rgb({color[0]},{color[1]},{color[2]}); margin: 6px 10px;"
        )


class CustomMenu(QWidget):
    """Dark popup menu widget (replaces QMenu on Cinnamon)."""

    def __init__(self, bg_color: tuple = (46, 46, 51), fg_color: tuple = (255, 255, 255)):
        super().__init__()
        self.bg_color = bg_color
        self.fg_color = fg_color

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        border_color = tuple(min(255, c + 15) for c in bg_color)
        self.setStyleSheet(
            f"QWidget {{ background-color: rgb({bg_color[0]},{bg_color[1]},{bg_color[2]}); "
            f"border: 1px solid rgb({border_color[0]},{border_color[1]},{border_color[2]}); "
            "border-radius: 6px; }}"
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(3, 3, 3, 3)
        self.layout.setSpacing(2)

        self.items: list = []

    def addItem(self, text, callback=None, icon=None, checkable=False):
        item = CustomMenuItem(text, icon, self.bg_color, self.fg_color, checkable=checkable)
        if callback:
            item.clicked.connect(callback)
        self.layout.addWidget(item)
        self.items.append(item)
        return item

    def addSeparator(self):
        sep = CustomMenuSeparator(tuple(max(0, c - 10) for c in self.bg_color))
        self.layout.addWidget(sep)

    def popup(self, pos):
        self.adjustSize()
        menu_height = self.height()
        adjusted = pos - QPoint(0, menu_height + 5)
        screen = QDesktopWidget().screenGeometry()
        if adjusted.y() < 0:
            adjusted.setY(pos.y() + 5)
        if adjusted.x() + self.width() > screen.width():
            adjusted.setX(screen.width() - self.width())
        self.move(adjusted)
        self.show()
        self.raise_()
        self.activateWindow()


class QMenuWrapper:
    """Wraps CustomMenu to expose a QMenu-compatible API."""

    def __init__(self, custom_menu: CustomMenu):
        self.custom_menu = custom_menu
        self.actions: list = []

    def addAction(self, action_or_text, callback=None):
        from PyQt5.QtWidgets import QAction

        if isinstance(action_or_text, QAction):
            action = action_or_text
            checkable = action.isCheckable()
            item = self.custom_menu.addItem(
                action.text(), None, action.icon(), checkable=checkable,
            )
            item.setEnabled(action.isEnabled())
            if checkable:
                item.setChecked(action.isChecked())

            def _on_click():
                if checkable:
                    new_state = not action.isChecked()
                    action.setChecked(new_state)
                    item.setChecked(new_state)
                    action.triggered.emit()
                else:
                    action.trigger()

            item.clicked.connect(_on_click)
            self.actions.append((action, item))
        else:
            item = self.custom_menu.addItem(action_or_text, callback)
            self.actions.append((None, item))

    def addSeparator(self):
        self.custom_menu.addSeparator()

    def popup(self, pos):
        self.custom_menu.popup(pos)

    def hide(self):
        self.custom_menu.hide()

    def setFont(self, font):
        pass  # Custom menu handles fonts internally

    def __getattr__(self, name):
        return getattr(self.custom_menu, name)


# ---------------------------------------------------------------------------
# CinnamonAdapter
# ---------------------------------------------------------------------------

class CinnamonAdapter(BaseUIAdapter):
    """UI adapter for Cinnamon — uses CustomMenu instead of native QMenu."""

    def __init__(self):
        super().__init__()
        self.theme_colors = self.get_theme_colors()

    def show_menu(self) -> None:
        pass  # Popup handled externally

    def update_layout_indicator(self, layout_name: str) -> None:
        pass  # Handled by TrayIcon

    def create_menu(self, parent=None):
        """Create a custom themed menu wrapped in QMenuWrapper."""
        bg = self.theme_colors.get("bg_color", (46, 46, 51))
        fg = self.theme_colors.get("fg_color", (255, 255, 255))
        custom_menu = CustomMenu(bg, fg)
        return QMenuWrapper(custom_menu)

    def supports_native_menu(self) -> bool:
        return False

    def get_theme_colors(self) -> dict:
        return {
            "bg_color": (46, 46, 51),
            "fg_color": (255, 255, 255),
            "base_color": (35, 38, 41),
        }
