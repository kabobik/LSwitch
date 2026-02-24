#!/usr/bin/env python3
"""Утилиты для работы с темами различных DE"""

from __future__ import annotations
import os
import re
from pathlib import Path
import sys
from typing import Optional

import lswitch.system as _system_mod

_theme_system = None

def set_system(sys_impl) -> None:
    global _theme_system
    _theme_system = sys_impl


def get_system():
    if _theme_system is not None:
        return _theme_system
    return getattr(_system_mod, 'SYSTEM', _system_mod)


def get_cinnamon_theme_colors() -> Optional[dict[str, tuple[int, int, int]]]:
    """
    Получает цвета темы Cinnamon из GTK файлов
    
    Returns:
        dict: {'bg_color': tuple, 'fg_color': tuple, 'base_color': tuple} или None
    """
    try:
        # Получаем имя темы из dconf
        result = get_system().run(['gsettings', 'get', 'org.cinnamon.desktop.interface', 'gtk-theme'], capture_output=True, text=True, timeout=2)
        
        if result.returncode != 0:
            return None
        
        theme_name = result.stdout.strip().strip("'\"")
        theme_path = Path(f'/usr/share/themes/{theme_name}/gtk-3.0/gtk.css')
        
        if not theme_path.exists():
            return None
        
        colors = {}
        content = theme_path.read_text()
        
        # Ищем определения цветов
        color_patterns = {
            'bg_color': r'@define-color\s+(?:theme_bg_color|bg_color)\s+#([0-9a-fA-F]{6});',
            'fg_color': r'@define-color\s+(?:theme_fg_color|fg_color)\s+#([0-9a-fA-F]{6});',
            'base_color': r'@define-color\s+(?:theme_base_color|base_color)\s+#([0-9a-fA-F]{6});'
        }
        
        for key, pattern in color_patterns.items():
            match = re.search(pattern, content)
            if match:
                hex_color = match.group(1)
                colors[key] = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        if colors:
            return colors
        
    except Exception as e:
        print(f"Ошибка чтения темы Cinnamon: {e}")
    
    return None


def get_kde_theme_colors() -> Optional[dict[str, tuple[int, int, int]]]:  
    """
    Получает цвета темы KDE из kdeglobals
    
    Returns:
        dict: {'bg_color': tuple, 'fg_color': tuple, 'base_color': tuple} или None
    """
    try:
        kdeglobals_path = Path.home() / '.config' / 'kdeglobals'
        
        if not kdeglobals_path.exists():
            return None
        
        content = kdeglobals_path.read_text()
        colors = {}
        
        # Ищем секцию [Colors:Window]
        window_section = re.search(r'\[Colors:Window\](.*?)(?=\[|\Z)', content, re.DOTALL)
        if window_section:
            section_text = window_section.group(1)
            
            # BackgroundNormal=46,52,64
            bg_match = re.search(r'BackgroundNormal=(\d+),(\d+),(\d+)', section_text)
            if bg_match:
                colors['bg_color'] = tuple(int(bg_match.group(i)) for i in (1, 2, 3))
            
            # ForegroundNormal=211,218,227
            fg_match = re.search(r'ForegroundNormal=(\d+),(\d+),(\d+)', section_text)
            if fg_match:
                colors['fg_color'] = tuple(int(fg_match.group(i)) for i in (1, 2, 3))
        
        # Ищем секцию [Colors:View] для base_color
        view_section = re.search(r'\[Colors:View\](.*?)(?=\[|\Z)', content, re.DOTALL)
        if view_section:
            section_text = view_section.group(1)
            base_match = re.search(r'BackgroundNormal=(\d+),(\d+),(\d+)', section_text)
            if base_match:
                colors['base_color'] = tuple(int(base_match.group(i)) for i in (1, 2, 3))
        
        if colors:
            return colors
            
    except Exception as e:
        print(f"Ошибка чтения темы KDE: {e}")
    
    return None


def get_theme_colors(de_name: str) -> Optional[dict[str, tuple[int, int, int]]]:  
    """
    Получает цвета темы для указанного DE
    
    Args:
        de_name: Имя DE ('cinnamon', 'kde', etc.)
    
    Returns:
        dict: {'bg_color': tuple, 'fg_color': tuple, 'base_color': tuple} или None
    """
    if de_name == 'cinnamon':
        return get_cinnamon_theme_colors()
    elif de_name == 'kde':
        return get_kde_theme_colors()
    
    # Fallback - попробуем Cinnamon метод
    return get_cinnamon_theme_colors()


def get_default_dark_colors() -> dict[str, tuple[int, int, int]]:
    """
    Возвращает цвета темной темы по умолчанию
    
    Returns:
        dict: Стандартные цвета темной темы
    """
    return {
        'bg_color': (46, 46, 51),
        'fg_color': (255, 255, 255),
        'base_color': (56, 56, 56)
    }


if __name__ == '__main__':
    # Тестирование
    from desktop import detect_desktop_environment
    
    de = detect_desktop_environment()
    print(f"Detected DE: {de}")
    
    colors = get_theme_colors(de)
    if colors:
        print("Theme colors:")
        for key, value in colors.items():
            print(f"  {key}: RGB{value}")
    else:
        print("Using default colors")
        colors = get_default_dark_colors()
        for key, value in colors.items():
            print(f"  {key}: RGB{value}")
