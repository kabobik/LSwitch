#!/usr/bin/env python3
"""Определение окружения рабочего стола и display server"""

from __future__ import annotations
import os


def detect_desktop_environment() -> str:
    """
    Определяет текущее окружение рабочего стола
    
    Returns:
        str: 'cinnamon', 'kde', 'gnome', 'xfce' или 'generic'
    """
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    session = os.environ.get('DESKTOP_SESSION', '').lower()
    
    # Проверяем различные DE
    if 'cinnamon' in desktop or 'cinnamon' in session:
        return 'cinnamon'
    elif 'kde' in desktop or 'plasma' in desktop:
        return 'kde'
    elif 'gnome' in desktop:
        return 'gnome'
    elif 'xfce' in desktop:
        return 'xfce'
    elif 'mate' in desktop:
        return 'mate'
    
    return 'generic'


def detect_display_server() -> str:
    """
    Определяет используемый display server
    
    Returns:
        str: 'wayland' или 'x11'
    """
    session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
    wayland_display = os.environ.get('WAYLAND_DISPLAY', '')
    
    if 'wayland' in session_type or wayland_display:
        return 'wayland'
    
    return 'x11'


def get_environment_info() -> dict[str, str]:
    """
    Возвращает полную информацию об окружении
    
    Returns:
        dict: {'de': str, 'display_server': str}
    """
    return {
        'de': detect_desktop_environment(),
        'display_server': detect_display_server()
    }


if __name__ == '__main__':
    # Тестирование
    info = get_environment_info()
    print(f"Desktop Environment: {info['de']}")
    print(f"Display Server: {info['display_server']}")
