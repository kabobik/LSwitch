#!/usr/bin/env python3
"""
Тестирование иконки трея
Запускает трей и показывает как выглядит иконка
"""

import sys
import os

# Добавляем родительскую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtCore import Qt


def create_simple_icon(color):
    """Создает упрощенную иконку клавиатуры одного цвета"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Рисуем простую клавиатуру
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    
    # Основной корпус клавиатуры
    painter.drawRoundedRect(8, 20, 48, 28, 3, 3)
    
    # Вырезаем клавиши (создаём эффект углублений)
    painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    
    # Ряд 1 - 6 клавиш
    for col in range(6):
        x = 12 + col * 7
        y = 24
        painter.drawRoundedRect(x, y, 5, 5, 1, 1)
    
    # Ряд 2 - 6 клавиш
    for col in range(6):
        x = 12 + col * 7
        y = 32
        painter.drawRoundedRect(x, y, 5, 5, 1, 1)
    
    # Ряд 3 - пробел
    painter.drawRoundedRect(16, 40, 32, 5, 1, 1)
    
    painter.end()
    return pixmap


def create_test_icon():
    """Создает тестовую иконку с обоими вариантами"""
    icon = QIcon()
    
    # Белая иконка для тёмной темы
    light_pixmap = create_simple_icon(QColor(255, 255, 255))
    icon.addPixmap(light_pixmap, QIcon.Normal)
    icon.addPixmap(light_pixmap, QIcon.Active)
    
    # Тёмная иконка для светлой темы
    dark_pixmap = create_simple_icon(QColor(50, 50, 50))
    icon.addPixmap(dark_pixmap, QIcon.Disabled)
    icon.addPixmap(dark_pixmap, QIcon.Selected)
    
    return icon


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # Создаем иконку
    icon = create_test_icon()
    
    # Создаем трей
    tray = QSystemTrayIcon(icon)
    
    # Простое меню
    menu = QMenu()
    
    light_action = QAction("Светлая тема (тёмная иконка)", menu)
    menu.addAction(light_action)
    
    dark_action = QAction("Тёмная тема (белая иконка)", menu)
    menu.addAction(dark_action)
    
    menu.addSeparator()
    
    quit_action = QAction("Выход", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    
    tray.setContextMenu(menu)
    tray.show()
    
    tray.showMessage(
        "Тест иконки",
        "Иконка должна адаптироваться к теме системы",
        QSystemTrayIcon.Information,
        3000
    )
    
    print("Тестовая иконка запущена. Проверьте системный трей.")
    print("Иконка должна быть:")
    print("  - Белой на тёмном фоне (тёмная тема)")
    print("  - Тёмной на светлом фоне (светлая тема)")
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
