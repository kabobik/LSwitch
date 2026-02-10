#!/usr/bin/env python3
"""
Тестовый скрипт для проверки адаптеров
"""

import sys
import os

# Тестируем определение DE
from lswitch.utils.desktop import detect_desktop_environment, detect_display_server, get_environment_info

print("=== Тест определения окружения ===")
de = detect_desktop_environment()
display = detect_display_server()
info = get_environment_info()

print(f"Desktop Environment: {de}")
print(f"Display Server: {display}")
print(f"Полная информация: {info}")
print()

# Тестируем получение цветов темы
from lswitch.utils.theme import get_theme_colors, get_kde_theme_colors, get_cinnamon_theme_colors

print("=== Тест получения цветов темы ===")
colors = get_theme_colors(de)
print(f"Цвета темы для {de}: {colors}")
print()

# Тестируем адаптеры
from lswitch.adapters import get_adapter, CinnamonAdapter, KDEAdapter

print("=== Тест адаптеров ===")
adapter = get_adapter()
print(f"Выбран адаптер: {adapter.__class__.__name__}")
print(f"Поддерживает нативное QMenu: {adapter.supports_native_menu()}")
print(f"Цвета адаптера: {adapter.get_theme_colors()}")
print()

# Тестируем создание меню
if __name__ == '__main__':
    # Тестируем создание меню
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)

    menu = adapter.create_menu()
    print(f"Создано меню: {type(menu)}")
    print(f"Тип меню: {menu.__class__.__name__}")

    # Проверяем API
    try:
        from PyQt5.QtWidgets import QAction
        action = QAction("Тестовый пункт", None)
        menu.addAction(action)
        menu.addSeparator()
        print("✅ API addAction и addSeparator работает")
    except Exception as e:
        print(f"❌ Ошибка API: {e}")

    print("\n=== Тест завершён ===")
