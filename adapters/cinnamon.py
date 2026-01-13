#!/usr/bin/env python3
"""Адаптер GUI для Cinnamon Desktop Environment"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt5.QtWidgets import QDesktopWidget
from PyQt5.QtGui import QIcon
from adapters.base import BaseGUIAdapter
from utils.theme import get_cinnamon_theme_colors, get_default_dark_colors


class CustomMenuItem(QWidget):
    """Кастомный пункт меню с темной темой"""
    clicked = pyqtSignal()
    
    def __init__(self, text, icon=None, bg_color=(46,46,51), fg_color=(255,255,255), checkable=False):
        super().__init__()
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.hover_color = tuple(min(255, c + 20) for c in bg_color)
        self._enabled = True
        self.checkable = checkable
        self.checkbox = None
        
        self.setMinimumHeight(28)  # Увеличили для лучшего отображения
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)  # Уменьшили отступы
        layout.setSpacing(8)
        
        # Если это checkable элемент, добавляем чекбокс
        if checkable:
            self.checkbox = QCheckBox()
            self.checkbox.setFixedSize(16, 16)  # Фиксированный размер для выравнивания
            self.checkbox.setStyleSheet(f"""
                QCheckBox {{
                    spacing: 0px;
                }}
                QCheckBox::indicator {{
                    width: 16px;
                    height: 16px;
                }}
                QCheckBox::indicator:unchecked {{
                    background-color: rgb(60, 60, 65);
                    border: 1px solid rgb(100, 100, 105);
                    border-radius: 3px;
                }}
                QCheckBox::indicator:checked {{
                    background-color: rgb(52, 152, 219);
                    border: 1px solid rgb(41, 128, 185);
                    border-radius: 3px;
                    image: url(none);
                }}
                QCheckBox::indicator:checked::after {{
                    content: "✓";
                }}
            """)
            self.checkbox.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(self.checkbox)
            self.icon_label = None
        else:
            # Иконка для обычных пунктов (или пустое место для выравнивания)
            self.icon_label = QLabel()
            self.icon_label.setFixedSize(16, 16)  # Такой же размер как чекбокс
            self.icon_label.setScaledContents(True)  # Масштабировать содержимое
            if icon and not icon.isNull():
                pixmap = icon.pixmap(QSize(16, 16))
                self.icon_label.setPixmap(pixmap)
            layout.addWidget(self.icon_label)
        
        self.label = QLabel(text)
        self.label.setStyleSheet(f"""
            color: rgb({fg_color[0]}, {fg_color[1]}, {fg_color[2]}); 
            background: transparent; 
            font-size: 14px;
            border: none;
            padding: 0;
        """)
        layout.addWidget(self.label)
        layout.addStretch()
        
        self.updateStyle(False)
    
    def setChecked(self, checked):
        """Устанавливает состояние чекбокса"""
        if self.checkbox:
            self.checkbox.setChecked(checked)
    
    def isChecked(self):
        """Возвращает состояние чекбокса"""
        if self.checkbox:
            return self.checkbox.isChecked()
        return False
    
    def setIcon(self, icon):
        """Обновляет иконку элемента"""
        if self.icon_label and not icon.isNull():
            pixmap = icon.pixmap(QSize(16, 16))
            self.icon_label.setPixmap(pixmap)
            self.icon_label.repaint()
            self.update()
        elif self.icon_label:
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
            font-size: 14px;
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


class CustomSubmenuItem(QWidget):
    """Пункт меню с подменю"""
    def __init__(self, text, submenu, icon=None, bg_color=(46,46,51), fg_color=(255,255,255)):
        super().__init__()
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.hover_color = tuple(min(255, c + 20) for c in bg_color)
        self.submenu = submenu
        
        self.setMinimumHeight(28)  # Такая же высота как у обычных пунктов
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)  # Такие же отступы
        layout.setSpacing(8)
        
        # Иконка с фиксированным размером для выравнивания
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)  # Такой же размер как у обычных пунктов
        self.icon_label.setScaledContents(True)
        if icon and not icon.isNull():
            pixmap = icon.pixmap(QSize(16, 16))
            self.icon_label.setPixmap(pixmap)
        layout.addWidget(self.icon_label)
        
        # Текст
        self.label = QLabel(text)
        self.label.setStyleSheet(f"""
            color: rgb({fg_color[0]}, {fg_color[1]}, {fg_color[2]}); 
            background: transparent; 
            font-size: 14px;
            border: none;
            padding: 0;
        """)
        layout.addWidget(self.label)
        layout.addStretch()
        
        # Стрелка вправо
        arrow = QLabel("▸")
        arrow.setStyleSheet(f"color: rgb({fg_color[0]}, {fg_color[1]}, {fg_color[2]}); background: transparent; font-size: 12px;")
        layout.addWidget(arrow)
        
        self.updateStyle(False)
    
    def updateStyle(self, hover):
        color = self.hover_color if hover else self.bg_color
        self.setStyleSheet(f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); border: none;")
    
    def enterEvent(self, event):
        self.updateStyle(True)
        # Показываем подменю справа от текущего пункта
        global_pos = self.mapToGlobal(QPoint(self.width(), 0))
        self.submenu.popup(global_pos)
    
    def leaveEvent(self, event):
        # Проверяем, не навели ли на подменю
        cursor_pos = self.mapToGlobal(self.mapFromGlobal(self.cursor().pos()))
        submenu_rect = self.submenu.geometry()
        if not submenu_rect.contains(self.submenu.mapFromGlobal(self.cursor().pos())):
            self.updateStyle(False)


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
        self.layout.setContentsMargins(3, 3, 3, 3)  # Было (4, 5, 4, 5)
        self.layout.setSpacing(2)  # Было 3
        
        self.items = []
    
    def addItem(self, text, callback=None, icon=None, checkable=False):
        """Добавить пункт меню"""
        item = CustomMenuItem(text, icon, self.bg_color, self.fg_color, checkable=checkable)
        if callback:
            item.clicked.connect(callback)
        self.layout.addWidget(item)
        self.items.append(item)
        return item
    
    def addSeparator(self):
        """Добавить разделитель"""
        sep = CustomMenuSeparator(tuple(max(0, c - 10) for c in self.bg_color))
        self.layout.addWidget(sep)
    
    def addSubmenuItem(self, text, submenu, icon=None):
        """Добавить пункт с подменю"""
        item = CustomSubmenuItem(text, submenu, icon, self.bg_color, self.fg_color)
        self.layout.addWidget(item)
        return item
    
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
        self.submenus = []  # Сохраняем ссылки на подменю
    
    def addAction(self, action_or_text, callback=None):
        """Добавляет QAction или текст в меню"""
        from PyQt5.QtWidgets import QAction
        
        if isinstance(action_or_text, QAction):
            action = action_or_text
            text = action.text()
            enabled = action.isEnabled()
            icon = action.icon()
            checkable = action.isCheckable()
            
            # Создаём CustomMenuItem с иконкой или чекбоксом
            item = self.custom_menu.addItem(text, None, icon, checkable=checkable)
            item.setEnabled(enabled)
            
            # Если checkable, синхронизируем состояние
            if checkable:
                item.setChecked(action.isChecked())
            
            # Связываем triggered с clicked
            def on_item_clicked():
                if checkable:
                    # Для checkable переключаем состояние
                    new_state = not action.isChecked()
                    action.setChecked(new_state)
                    item.setChecked(new_state)
                action.trigger()
            
            item.clicked.connect(on_item_clicked)
            
            # Синхронизируем изменения QAction с CustomMenuItem
            def sync_state():
                if checkable:
                    item.setChecked(action.isChecked())
                elif not action.icon().isNull():
                    pixmap = action.icon().pixmap(QSize(24, 24))
                    if item.icon_label:
                        item.icon_label.setPixmap(pixmap)
                        item.icon_label.repaint()
            
            def sync_enabled(enabled):
                item.setEnabled(enabled)
            
            action.changed.connect(sync_state)
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
    
    def addMenu(self, submenu_or_text):
        """Добавляет подменю (настоящее раскрывающееся подменю)"""
        from PyQt5.QtWidgets import QMenu
        
        if isinstance(submenu_or_text, QMenu):
            # Если это QMenu, создаем CustomMenu для подменю
            submenu_qmenu = submenu_or_text
            self.submenus.append(submenu_qmenu)  # Сохраняем ссылку!
            
            title = submenu_qmenu.title()
            icon = submenu_qmenu.icon()
            
            # Создаем CustomMenu для отображения подменю
            submenu_widget = CustomMenu(self.custom_menu.bg_color, self.custom_menu.fg_color)
            submenu_wrapper = QMenuWrapper(submenu_widget)
            
            # Добавляем все action из QMenu в CustomMenu
            for action in submenu_qmenu.actions():
                if action.isSeparator():
                    submenu_wrapper.addSeparator()
                else:
                    submenu_wrapper.addAction(action)
            
            # Добавляем пункт с подменю
            self.custom_menu.addSubmenuItem(title, submenu_widget, icon)
            
            return submenu_qmenu
        else:
            # Создаем новое подменю и возвращаем обертку
            from PyQt5.QtWidgets import QMenu as QtMenu
            submenu = QtMenu(submenu_or_text)
            self.submenus.append(submenu)  # Сохраняем ссылку!
            return submenu
    
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
