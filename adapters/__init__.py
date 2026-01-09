"""Адаптеры GUI для различных окружений рабочего стола"""

import sys
sys.path.insert(0, '/home/anton/VsCode/LSwitch')

from adapters.base import BaseGUIAdapter
from adapters.cinnamon import CinnamonAdapter
from adapters.kde import KDEAdapter
from utils.desktop import detect_desktop_environment


def get_adapter():
    """
    Фабричная функция для получения подходящего адаптера
    Returns:
        BaseGUIAdapter: Адаптер для текущего DE
    """
    de = detect_desktop_environment()
    
    if de == 'cinnamon':
        return CinnamonAdapter()
    elif de == 'kde':
        return KDEAdapter()
    else:
        # По умолчанию используем CinnamonAdapter (более универсальный)
        print(f"Warning: Unknown DE '{de}', using CinnamonAdapter as fallback")
        return CinnamonAdapter()


__all__ = ['BaseGUIAdapter', 'CinnamonAdapter', 'KDEAdapter', 'get_adapter']
