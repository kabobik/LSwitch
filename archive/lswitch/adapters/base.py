#!/usr/bin/env python3
"""Базовый класс адаптера GUI"""

from abc import ABC, abstractmethod


class BaseGUIAdapter(ABC):
    """Базовый класс для адаптеров GUI различных DE"""
    
    def __init__(self):
        self.theme_colors = None
    
    @abstractmethod
    def create_menu(self, parent=None):
        """
        Создает меню для системного трея
        
        Args:
            parent: Родительский виджет
            
        Returns:
            QMenu или кастомный Menu объект
        """
        pass
    
    @abstractmethod
    def get_theme_colors(self):
        """
        Получает цвета текущей темы DE
        
        Returns:
            dict: {'bg_color': tuple, 'fg_color': tuple, 'base_color': tuple}
        """
        pass
    
    def apply_theme_to_menu(self, menu):
        """
        Применяет цвета темы к меню (опционально)
        
        Args:
            menu: Объект меню
        """
        pass
    
    def supports_native_menu(self):
        """
        Возвращает True если DE поддерживает нативное QMenu с темами
        
        Returns:
            bool
        """
        return False
