#!/usr/bin/env python3
"""Адаптер GUI для Cinnamon Desktop Environment"""

import sys
sys.path.insert(0, '/home/anton/VsCode/LSwitch')

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt5.QtWidgets import QDesktopWidget
from PyQt5.QtGui import QIcon
from adapters.base import BaseGUIAdapter
from utils.theme import get_cinnamon_theme_colors, get_default_dark_colors


class CustomMenuItem(QWidget):
    """Кастомный пункт меню с темной темой"""
    clicked = pyqtSignal()
    
    def __init__(self, text, icon=None, bg_color=(46,46,51), fg_color=(255,255,255)):
        super().__init__()
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.hover_color = tuple(min(255, c + 20) for c in bg_color)
        self._enabled = True
        
        self.setMinimumHeight(48)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(18)
        
        # Всегда создаём icon_label для возможности обновления
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        if icon and not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(QSize(24, 24)))
        layout.addWidget(self.icon_label)
        
        self.label = QLabel(text)
        self.label.setStyleSheet(f"""
            color: rgb({fg_color[0]}, {fg_color[1]}, {fg_color[2]}); 
            background: transparent; 
            font-size: 24px;
            border: none;
            padding: 0;
        """)
        layout.addWidget(self.label)
        layout.addStretch()
        
        self.updateStyle(False)
    
    def setIcon(self, icon):
        """Обновляет иконку элемента"""
        if not icon.isNull():
            pixmap = icon.pixmap(QSize(24, 24))
            self.icon_label.setPixmap(pixmap)
            self.icon_label.update()  # Принудительно перерисовываем
        else:
            self.icon_label.clear()
    
    def setEnabled(self, enabled):
        self._enabled = enabled
        if enabled:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.updateStyle(False)
    
    def updateStyle(self, hover):
        if not self._enabled:
            color = self.bg_color
            text_color = "rgb(100, 100, 105)"
        else:
            color = self.hover_color if hover else self.bg_color
            text_color = f"rgb({self.fg_color[0]}, {self.fg_color[1]}, {self.fg_color[2]})"
        
        self.label.setStyleSheet(f"""
            color: {text_color}; 
            background: transparent; 
            font-size: 24px;
            border: none;
            padding: 0;
        """)
        
        self.setStyleSheet(f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); border: none;")
    
    def enterEvent(self, event):
        if self._enabled:
            self.updateStyle(True)
    
    def leaveEvent(self, event):
        self.updateStyle(False)
    
    def mousePressEvent(self, event):
        if not self._enabled:
            return
        self.clicked.emit()


class CustomMenuSeparator(QWidget):
    """Разделитель для кастомного меню"""
    def __init__(self, color=(60,60,65)):
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet(f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); margin: 6px 10px;")


class CustomMenu(QWidget):
    """Кастомное темное меню вместо QMenu"""
    def __init__(self, bg_color=(46,46,51), fg_color=(255,255,255)):
        super().__init__()
        self.bg_color = bg_color
        self.fg_color = fg_color
        
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        
        border_color = tuple(min(255, c + 15) for c in bg_color)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
                border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});
                border-radius: 6px;
            }}
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 8, 6, 8)
        self.layout.setSpacing(5)
        
        self.items = []
    
    def addItem(self, text, callback=None, icon=None):
        """Добавить пункт меню"""
        item = CustomMenuItem(text, icon, self.bg_color, self.fg_color)
        if callback:
            item.clicked.connect(callback)
        self.layout.addWidget(item)
        self.items.append(item)
        return item
    
    def addSeparator(self):
        """Добавить разделитель"""
        sep = CustomMenuSeparator(tuple(max(0, c - 10) for c in self.bg_color))
        self.layout.addWidget(sep)
    
    def popup(self, pos):
        """Показать меню в указанной позиции (выше курсора для трея)"""
        self.adjustSize()
        
        menu_height = self.height()
        adjusted_pos = pos - QPoint(0, menu_height + 5)
        
        screen = QDesktopWidget().screenGeometry()
        
        # Проверяем что меню не выходит за верхнюю границу экрана
        if adjusted_pos.y() < 0:
            adjusted_pos.setY(pos.y() + 5)
        
        # Проверяем правую границу
        if adjusted_pos.x() + self.width() > screen.width():
            adjusted_pos.setX(screen.width() - self.width())
        
        self.move(adjusted_pos)
        self.show()
        self.raise_()
        self.activateWindow()


class QMenuWrapper:
    """Обертка для CustomMenu с API совместимым с QMenu"""
    
    def __init__(self, custom_menu):
        self.custom_menu = custom_menu
        self.actions = []
    
    def addAction(self, action_or_text, callback=None):
        """Добавляет QAction или текст в меню"""
        from PyQt5.QtWidgets import QAction
        
        if isinstance(action_or_text, QAction):
            action = action_or_text
            text = action.text()
            enabled = action.isEnabled()
            icon = action.icon()
            
            # Создаём CustomMenuItem с иконкой
            item = self.custom_menu.addItem(text, None, icon)
            item.setEnabled(enabled)
            
            # Связываем triggered с clicked
            item.clicked.connect(action.trigger)
            
            # Синхронизируем изменения QAction с CustomMenuItem
            def sync_icon():
                new_icon = action.icon()
                if not new_icon.isNull():
                    # Получаем pixmap напрямую из иконки
                    pixmap = new_icon.pixmap(QSize(24, 24))
                    item.icon_label.setPixmap(pixmap)
                    item.icon_label.repaint()  # Принудительная перерисовка
            
            def sync_enabled(enabled):
                item.setEnabled(enabled)
            
            action.changed.connect(sync_icon)
            action.changed.connect(lambda: sync_enabled(action.isEnabled()))
            
            self.actions.append((action, item))
        else:
            # Простой текст + callback
            item = self.custom_menu.addItem(action_or_text, callback)
            self.actions.append((None, item))
        
        return action_or_text if isinstance(action_or_text, QAction) else None
    
    def addSeparator(self):
        """Добавляет разделитель"""
        self.custom_menu.addSeparator()
    
    def popup(self, pos):
        """Показывает меню"""
        self.custom_menu.popup(pos)
    
    def hide(self):
        """Скрывает меню"""
        self.custom_menu.hide()
    
    def __getattr__(self, name):
        """Проксируем все остальные методы к CustomMenu"""
        return getattr(self.custom_menu, name)


class CinnamonAdapter(BaseGUIAdapter):
    """Адаптер GUI для Cinnamon DE"""
    
    def __init__(self):
        super().__init__()
        self.theme_colors = self.get_theme_colors()
    
    def create_menu(self, parent=None):
        """Создает кастомное меню для Cinnamon с оберткой для совместимости с QMenu API"""
        bg_color = self.theme_colors.get('bg_color', (46, 46, 51))
        fg_color = self.theme_colors.get('fg_color', (255, 255, 255))
        custom_menu = CustomMenu(bg_color, fg_color)
        return QMenuWrapper(custom_menu)
    
    def get_theme_colors(self):
        """Получает цвета темы Cinnamon"""
        colors = get_cinnamon_theme_colors()
        if not colors:
            colors = get_default_dark_colors()
        return colors
    
    def supports_native_menu(self):
        """Cinnamon не поддерживает нативное QMenu с темами"""
        return False
