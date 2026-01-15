"""Адаптеры GUI для различных окружений рабочего стола"""

import sys
sys.path.insert(0, '/home/anton/VsCode/LSwitch')

from adapters.base import BaseGUIAdapter
from utils.desktop import detect_desktop_environment


def get_adapter():
    """
    Фабричная функция для получения подходящего адаптера
    Returns:
        BaseGUIAdapter: Адаптер для текущего DE
    """
    de = detect_desktop_environment()

    try:
        if de == 'cinnamon':
            from adapters.cinnamon import CinnamonAdapter
            return CinnamonAdapter()
        elif de == 'kde':
            from adapters.kde import KDEAdapter
            return KDEAdapter()
        else:
            # По умолчанию используем CinnamonAdapter (более универсальный)
            print(f"Warning: Unknown DE '{de}', using CinnamonAdapter as fallback")
            from adapters.cinnamon import CinnamonAdapter
            return CinnamonAdapter()
    except Exception as e:
        # If importing GUI adapters fails (e.g. PyQt5 missing), return None so tests can handle it
        print(f"⚠️  GUI adapter import failed: {e}")
        return None


__all__ = ['BaseGUIAdapter', 'get_adapter']
