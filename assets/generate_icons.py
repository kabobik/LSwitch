#!/usr/bin/env python3
"""
Генератор иконок LSwitch для светлой и тёмной темы
Создаёт PNG иконки разных размеров
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QPainter, QColor
from PyQt5.QtCore import Qt


def create_keyboard_icon(size, color):
    """Создаёт упрощённую иконку клавиатуры"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Масштабирующие коэффициенты
    scale = size / 64
    
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    
    # Основной корпус клавиатуры
    painter.drawRoundedRect(
        int(8 * scale), int(20 * scale),
        int(48 * scale), int(28 * scale),
        int(3 * scale), int(3 * scale)
    )
    
    # Вырезаем клавиши
    painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    
    # Ряд 1 - 6 клавиш
    for col in range(6):
        x = int((12 + col * 7) * scale)
        y = int(24 * scale)
        w = int(5 * scale)
        h = int(5 * scale)
        r = int(1 * scale)
        painter.drawRoundedRect(x, y, w, h, r, r)
    
    # Ряд 2 - 6 клавиш  
    for col in range(6):
        x = int((12 + col * 7) * scale)
        y = int(32 * scale)
        w = int(5 * scale)
        h = int(5 * scale)
        r = int(1 * scale)
        painter.drawRoundedRect(x, y, w, h, r, r)
    
    # Ряд 3 - пробел
    painter.drawRoundedRect(
        int(16 * scale), int(40 * scale),
        int(32 * scale), int(5 * scale),
        int(1 * scale), int(1 * scale)
    )
    
    painter.end()
    return pixmap


def main():
    app = QApplication(sys.argv)
    
    sizes = [16, 22, 24, 32, 48, 64, 128, 256]
    
    # Белая иконка для тёмной темы
    light_color = QColor(255, 255, 255)
    for size in sizes:
        pixmap = create_keyboard_icon(size, light_color)
        filename = f"lswitch-light-{size}.png"
        pixmap.save(filename)
        print(f"✓ Создана {filename}")
    
    # Тёмная иконка для светлой темы
    dark_color = QColor(50, 50, 50)
    for size in sizes:
        pixmap = create_keyboard_icon(size, dark_color)
        filename = f"lswitch-dark-{size}.png"
        pixmap.save(filename)
        print(f"✓ Создана {filename}")
    
    print(f"\n✓ Создано {len(sizes) * 2} иконок")
    print("  - lswitch-light-*.png - для тёмной темы (белые)")
    print("  - lswitch-dark-*.png - для светлой темы (тёмные)")


if __name__ == '__main__':
    main()
