#!/usr/bin/env python3
"""Адаптер GUI для KDE Plasma Desktop Environment"""

from PyQt5.QtWidgets import QMenu, QAction
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt
from adapters.base import BaseGUIAdapter
from utils.theme import get_kde_theme_colors, get_default_dark_colors


class KDEAdapter(BaseGUIAdapter):
    """Адаптер GUI для KDE Plasma"""
    
    def __init__(self):
        super().__init__()
        self.theme_colors = self.get_theme_colors()
    
    def create_menu(self, parent=None):
        """
        Создает нативное QMenu для KDE
        KDE корректно применяет темы к QMenu
        """
        # QMenu не может принимать QSystemTrayIcon как parent
        # Используем None для корректной работы
        menu = QMenu(None)
        
        # Применяем палитру темы
        palette = menu.palette()
        bg_color = self.theme_colors.get('bg_color', (46, 52, 64))
        fg_color = self.theme_colors.get('fg_color', (211, 218, 227))
        
        palette.setColor(QPalette.Window, QColor(*bg_color))
        palette.setColor(QPalette.WindowText, QColor(*fg_color))
        palette.setColor(QPalette.Base, QColor(*self.theme_colors.get('base_color', bg_color)))
        palette.setColor(QPalette.Text, QColor(*fg_color))
        palette.setColor(QPalette.Button, QColor(*bg_color))
        palette.setColor(QPalette.ButtonText, QColor(*fg_color))
        
        # Цвета для hover
        hover_color = tuple(min(255, c + 20) for c in bg_color)
        palette.setColor(QPalette.Highlight, QColor(*hover_color))
        palette.setColor(QPalette.HighlightedText, QColor(*fg_color))
        
        menu.setPalette(palette)
        
        # Стилизация для лучшей интеграции
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
                color: rgb({fg_color[0]}, {fg_color[1]}, {fg_color[2]});
                border: 1px solid rgba({fg_color[0]}, {fg_color[1]}, {fg_color[2]}, 0.2);
                padding: 6px;
                font-size: 11pt;
            }}
            QMenu::item {{
                padding: 8px 20px;
                min-height: 32px;
            }}
            QMenu::item:selected {{
                background-color: rgb({hover_color[0]}, {hover_color[1]}, {hover_color[2]});
            }}
            QMenu::item:disabled {{
                color: rgb(100, 100, 105);
            }}
            QMenu::separator {{
                height: 1px;
                background-color: rgba({fg_color[0]}, {fg_color[1]}, {fg_color[2]}, 0.2);
                margin: 4px 10px;
            }}
        """)
        
        return menu
    
    def get_theme_colors(self):
        """Получает цвета темы KDE"""
        colors = get_kde_theme_colors()
        if not colors:
            # Fallback - используем стандартные цвета Breeze Dark
            colors = {
                'bg_color': (49, 54, 59),
                'fg_color': (239, 240, 241),
                'base_color': (35, 38, 41)
            }
        return colors
    
    def supports_native_menu(self):
        """KDE поддерживает нативное QMenu с темами"""
        return True
    
    def apply_theme_to_menu(self, menu):
        """Дополнительная настройка меню (если нужна)"""
        # Уже применено в create_menu
        pass
