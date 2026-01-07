#!/usr/bin/env python3
"""
LSwitch - GUI трей приложение
Системный трей с меню для управления переключателем раскладки
"""

import sys
import os
import json
import signal
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtCore import QProcess, Qt


class LSwitchTray(QSystemTrayIcon):
    """Системный трей для LSwitch"""
    
    def __init__(self, icon, parent=None):
        super().__init__(icon, parent)
        
        self.config_path = self.find_config_path()
        self.config = self.load_config()
        self.process = None
        
        # Создаем меню
        self.menu = QMenu()
        
        # Чекбокс для автопереключения
        self.auto_switch_action = QAction("Автоперек⁣лючение", self.menu)
        self.auto_switch_action.setCheckable(True)
        self.auto_switch_action.setChecked(self.config.get('auto_switch', False))
        self.auto_switch_action.triggered.connect(self.toggle_auto_switch)
        self.menu.addAction(self.auto_switch_action)
        
        self.menu.addSeparator()
        
        # Статус службы
        self.status_action = QAction("Статус: Запущен", self.menu)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        
        self.menu.addSeparator()
        
        # О программе
        about_action = QAction("О программе", self.menu)
        about_action.triggered.connect(self.show_about)
        self.menu.addAction(about_action)
        
        self.menu.addSeparator()
        
        # Выход
        exit_action = QAction("Выход", self.menu)
        exit_action.triggered.connect(self.quit_application)
        self.menu.addAction(exit_action)
        
        self.setContextMenu(self.menu)
        
        # Обработка клика по иконке
        self.activated.connect(self.on_tray_activated)
        
        # Запускаем основной процесс
        self.start_lswitch()
        
    def find_config_path(self):
        """Определяет путь к файлу конфигурации"""
        system_config = '/etc/lswitch/config.json'
        local_config = os.path.join(os.path.dirname(__file__), 'config.json')
        
        if os.path.exists(system_config):
            return system_config
        return local_config
    
    def load_config(self):
        """Загружает конфигурацию"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки конфигурации: {e}", file=sys.stderr, flush=True)
            return {}
    
    def save_config(self):
        """Сохраняет конфигурацию"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            print(f"Конфигурация сохранена: {self.config_path}", flush=True)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}", file=sys.stderr, flush=True)
            self.showMessage(
                "Ошибка",
                f"Не удалось сохранить настройки: {e}",
                QSystemTrayIcon.Critical,
                3000
            )
    
    def toggle_auto_switch(self, checked):
        """Переключает режим автопереключения"""
        self.config['auto_switch'] = checked
        self.save_config()
        
        status = "включено" if checked else "выключено"
        self.showMessage(
            "LSwitch",
            f"Автопереключение {status}",
            QSystemTrayIcon.Information,
            2000
        )
        
        # Перезапускаем процесс для применения изменений
        self.restart_lswitch()
    
    def start_lswitch(self):
        """Запускает основной процесс lswitch"""
        if self.process and self.process.state() == QProcess.Running:
            return
        
        self.process = QProcess()
        
        # Определяем путь к исполняемому файлу
        script_path = os.path.join(os.path.dirname(__file__), 'lswitch.py')
        if not os.path.exists(script_path):
            script_path = '/usr/local/bin/lswitch'
        
        self.process.start('python3', ['-u', script_path])
        
        if self.process.waitForStarted(3000):
            print("LSwitch процесс запущен", flush=True)
            self.status_action.setText("Статус: Запущен")
        else:
            print("Ошибка запуска LSwitch", file=sys.stderr, flush=True)
            self.status_action.setText("Статус: Ошибка")
            self.showMessage(
                "Ошибка",
                "Не удалось запустить службу LSwitch",
                QSystemTrayIcon.Critical,
                3000
            )
    
    def stop_lswitch(self):
        """Останавливает основной процесс"""
        if self.process and self.process.state() == QProcess.Running:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
            print("LSwitch процесс остановлен", flush=True)
            self.status_action.setText("Статус: Остановлен")
    
    def restart_lswitch(self):
        """Перезапускает процесс"""
        self.stop_lswitch()
        self.start_lswitch()
    
    def on_tray_activated(self, reason):
        """Обработка клика по иконке в трее"""
        if reason == QSystemTrayIcon.Trigger:  # Левый клик
            # Показываем меню
            self.contextMenu().popup(QApplication.instance().desktop().cursor().pos())
    
    def show_about(self):
        """Показывает информацию о программе"""
        self.showMessage(
            "LSwitch v1.0",
            "Умный переключатель раскладки клавиатуры\n"
            "Двойной Shift для переключения и конвертации текста\n\n"
            "© 2026 Anton",
            QSystemTrayIcon.Information,
            5000
        )
    
    def quit_application(self):
        """Выход из приложения"""
        self.stop_lswitch()
        QApplication.instance().quit()


def main():
    """Главная функция"""
    # Настройка unbuffered вывода
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
    
    # Обработка сигналов для корректного завершения
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    
    # Не завершаем приложение при закрытии последнего окна
    app.setQuitOnLastWindowClosed(False)
    
    # Создаем адаптивную иконку для темной и светлой темы
    icon = create_adaptive_icon()
    
    # Создаем трей
    tray = LSwitchTray(icon)
    tray.show()
    
    print("LSwitch GUI запущен", flush=True)
    tray.showMessage(
        "LSwitch",
        "Служба запущена и работает в фоне",
        QSystemTrayIcon.Information,
        2000
    )
    
    sys.exit(app.exec_())


def create_adaptive_icon():
    """Создает иконку, адаптированную к теме системы"""
    # Определяем путь к иконке
    icon_path = os.path.join(os.path.dirname(__file__), 'lswitch.svg')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(os.path.dirname(__file__), 'lswitch.png')
    if not os.path.exists(icon_path):
        icon_path = '/usr/share/pixmaps/lswitch.svg'
    
    # Пытаемся использовать системную иконку клавиатуры
    if os.path.exists(icon_path):
        icon = QIcon(icon_path)
    else:
        # Используем стандартную иконку клавиатуры
        icon = QIcon.fromTheme('input-keyboard', QIcon.fromTheme('preferences-desktop-keyboard'))
    
    # Если иконка пустая, создаем простую цветную иконку
    if icon.isNull():
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        
        # Определяем цвет на основе темы
        palette = QApplication.instance().palette()
        text_color = palette.color(palette.WindowText)
        
        # Рисуем простой прямоугольник (клавиатура)
        painter.setPen(text_color)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(8, 20, 48, 24, 4, 4)
        
        # Рисуем клавиши
        for row in range(2):
            for col in range(5):
                x = 12 + col * 8
                y = 24 + row * 8
                painter.fillRect(x, y, 6, 6, text_color)
        
        painter.end()
        icon = QIcon(pixmap)
    
    return icon


if __name__ == '__main__':
    main()
