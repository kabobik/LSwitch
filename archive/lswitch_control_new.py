#!/usr/bin/env python3
"""
LSwitch - GUI панель управления службой
Управляет systemd службой без запуска собственного процесса
Модульная версия с адаптерами под разные DE
"""

import sys
import os
import json
import signal
import subprocess
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QAction,
                             QMessageBox, QLabel)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette, QCursor
from PyQt5.QtCore import Qt, QTimer, QEvent, QPoint

# Импортируем адаптеры
sys.path.insert(0, '/home/anton/VsCode/LSwitch')
from adapters import get_adapter
from utils.desktop import detect_desktop_environment, detect_display_server


class LSwitchControlPanel(QSystemTrayIcon):
    """Панель управления в системном трее"""
    
    def __init__(self, icon, parent=None):
        super().__init__(icon, parent)
        
        # Определяем среду
        self.de = detect_desktop_environment()
        self.display_server = detect_display_server()
        print(f"Обнаружено: DE={self.de}, Display Server={self.display_server}", flush=True)
        
        # Получаем адаптер для текущего DE
        self.adapter = get_adapter()
        print(f"Используется адаптер: {self.adapter.__class__.__name__}", flush=True)
        
        # Загружаем конфигурацию
        self.config = self.load_config()
        
        # Создаём меню через адаптер
        self.create_tray_menu()
        
        # Обработка клика по иконке
        self.activated.connect(self.on_tray_activated)
        
        # Обновляем статус службы
        self.update_status()
        
        # Таймер для периодического обновления статуса
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(10000)  # Каждые 10 секунд
    
    def create_tray_menu(self):
        """Создаёт контекстное меню трея через адаптер"""
        # Создаём меню через адаптер
        self.menu = self.adapter.create_menu(self)
        
        # Проверяем, нужно ли использовать кастомное меню
        if not self.adapter.supports_native_menu():
            print("Используется кастомное меню (CustomMenu)", flush=True)
        else:
            print("Используется нативное QMenu", flush=True)
        
        # Заголовок меню
        title_action = QAction("⚡ LSwitch Control", self)
        title_action.setEnabled(False)
        self.menu.addAction(title_action)
        self.menu.addSeparator()
        
        # Управление службой
        self.start_action = QAction("▶️ Запустить службу", self)
        self.start_action.triggered.connect(self.start_service)
        self.menu.addAction(self.start_action)
        
        self.stop_action = QAction("⏸ Остановить службу", self)
        self.stop_action.triggered.connect(self.stop_service)
        self.menu.addAction(self.stop_action)
        
        self.restart_action = QAction("🔄 Перезапустить службу", self)
        self.restart_action.triggered.connect(self.restart_service)
        self.menu.addAction(self.restart_action)
        
        self.menu.addSeparator()
        
        # Автопереключение
        self.auto_switch_action = QAction("Автопереключение", self)
        self.auto_switch_action.setCheckable(True)
        self.auto_switch_action.setChecked(self.config.get('auto_switch', True))
        self.auto_switch_action.triggered.connect(lambda: self.toggle_auto_switch(self.auto_switch_action.isChecked()))
        self.menu.addAction(self.auto_switch_action)
        
        # Самообучающийся словарь
        self.user_dict_action = QAction("Самообучающийся словарь", self)
        self.user_dict_action.setCheckable(True)
        self.user_dict_action.setChecked(self.config.get('user_dict_enabled', False))
        self.user_dict_action.triggered.connect(lambda: self.toggle_user_dict(self.user_dict_action.isChecked()))
        self.menu.addAction(self.user_dict_action)
        
        # Автозапуск
        self.autostart_action = QAction("Автозапуск службы", self)
        self.autostart_action.setCheckable(True)
        autostart_enabled = self.get_service_status() == 'enabled'
        self.autostart_action.setChecked(autostart_enabled)
        self.autostart_action.triggered.connect(lambda: self.toggle_autostart(self.autostart_action.isChecked()))
        self.menu.addAction(self.autostart_action)
        
        self.menu.addSeparator()
        
        # Логи
        logs_action = QAction("📋 Показать логи", self)
        logs_action.triggered.connect(self.show_logs)
        self.menu.addAction(logs_action)
        
        # О программе
        about_action = QAction("ℹ️ О программе", self)
        about_action.triggered.connect(self.show_about)
        self.menu.addAction(about_action)
        
        self.menu.addSeparator()
        
        # Выход
        quit_action = QAction("❌ Выход из панели", self)
        quit_action.triggered.connect(self.quit_application)
        self.menu.addAction(quit_action)
        
        # Для нативного QMenu устанавливаем контекстное меню
        if self.adapter.supports_native_menu():
            self.setContextMenu(self.menu)
        # Для CustomMenu обрабатываем правый клик вручную
    
    def load_config(self):
        """Загружает конфигурацию из файла"""
        config_path = os.path.expanduser('~/.config/lswitch/config.json')
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Не удалось загрузить конфиг: {e}", file=sys.stderr, flush=True)
            return {
                'auto_switch': True,
                'user_dict_enabled': False,
                'dictionaries': []
            }
    
    def save_config(self):
        """Сохраняет конфигурацию в файл"""
        config_path = os.path.expanduser('~/.config/lswitch/config.json')
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception as e:
            print(f"Не удалось сохранить конфиг: {e}", file=sys.stderr, flush=True)
            return False
    
    def get_service_status(self):
        """Получает статус службы"""
        try:
            result = subprocess.run(
                ['systemctl', '--user', 'is-active', 'lswitch'],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.stdout.strip()
        except Exception:
            return 'unknown'
    
    def is_service_enabled(self):
        """Проверяет, включен ли автозапуск"""
        try:
            result = subprocess.run(
                ['systemctl', '--user', 'is-enabled', 'lswitch'],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.stdout.strip() == 'enabled'
        except Exception:
            return False
    
    def run_systemctl(self, action):
        """Выполняет команду systemctl"""
        try:
            subprocess.run(
                ['systemctl', '--user', action, 'lswitch'],
                check=True,
                timeout=10
            )
            return True
        except Exception as e:
            print(f"Ошибка systemctl {action}: {e}", file=sys.stderr, flush=True)
            return False
    
    def update_status(self):
        """Обновляет состояние кнопок в зависимости от статуса службы"""
        status = self.get_service_status()
        
        if status == 'active':
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(True)
            self.restart_action.setEnabled(True)
            self.setToolTip("LSwitch работает ✅")
        else:
            self.start_action.setEnabled(True)
            self.stop_action.setEnabled(False)
            self.restart_action.setEnabled(False)
            self.setToolTip("LSwitch остановлен ⏸")
    
    def start_service(self):
        """Запускает службу"""
        if self.run_systemctl('start'):
            self.showMessage("LSwitch", "Служба запущена", QSystemTrayIcon.Information, 2000)
        else:
            self.showMessage("Ошибка", "Не удалось запустить службу", QSystemTrayIcon.Critical, 3000)
        self.update_status()
    
    def stop_service(self):
        """Останавливает службу"""
        if self.run_systemctl('stop'):
            self.showMessage("LSwitch", "Служба остановлена", QSystemTrayIcon.Information, 2000)
        else:
            self.showMessage("Ошибка", "Не удалось остановить службу", QSystemTrayIcon.Critical, 3000)
        self.update_status()
    
    def restart_service(self):
        """Перезапускает службу"""
        if self.run_systemctl('restart'):
            self.showMessage("LSwitch", "Служба перезапущена", QSystemTrayIcon.Information, 2000)
        else:
            self.showMessage("Ошибка", "Не удалось перезапустить службу", QSystemTrayIcon.Critical, 3000)
        self.update_status()
    
    def toggle_auto_switch(self, checked):
        """Переключает режим автопереключения"""
        self.config['auto_switch'] = checked
        if self.save_config():
            # Отправляем сигнал службе для перезагрузки конфига
            self.reload_service_config()
            
            status = "включено" if checked else "выключено"
            self.showMessage(
                "LSwitch",
                f"Автопереключение {status}",
                QSystemTrayIcon.Information,
                2000
            )
    
    def toggle_user_dict(self, checked):
        """Переключает режим самообучающегося словаря"""
        self.config['user_dict_enabled'] = checked
        if self.save_config():
            # Отправляем сигнал службе для перезагрузки конфига
            self.reload_service_config()
            
            status = "включён" if checked else "выключен"
            msg = f"Самообучающийся словарь {status}"
            if checked:
                msg += "\n\nСистема будет запоминать ваши корректировки"
            self.showMessage(
                "LSwitch",
                msg,
                QSystemTrayIcon.Information,
                3000
            )
    
    def reload_service_config(self):
        """Перезагружает конфигурацию службы без перезапуска"""
        try:
            # Отправляем SIGHUP процессу lswitch
            subprocess.run(['pkill', '-HUP', '-f', 'lswitch.py'], timeout=2)
        except Exception as e:
            print(f"Не удалось отправить сигнал: {e}", file=sys.stderr, flush=True)
    
    def toggle_autostart(self, checked):
        """Включает/выключает автозапуск службы"""
        action = 'enable' if checked else 'disable'
        if self.run_systemctl(action):
            status = "включен" if checked else "выключен"
            self.showMessage(
                "LSwitch",
                f"Автозапуск {status}",
                QSystemTrayIcon.Information,
                2000
            )
            # Обновляем чекбокс
            self.autostart_action.setChecked(checked)
        else:
            self.showMessage(
                "Ошибка",
                f"Не удалось изменить автозапуск",
                QSystemTrayIcon.Critical,
                3000
            )
            # Возвращаем чекбокс обратно
            self.autostart_action.setChecked(not checked)
    
    def show_logs(self):
        """Показывает логи в терминале"""
        try:
            subprocess.Popen([
                'x-terminal-emulator', '-e',
                'journalctl', '-u', 'lswitch', '-f'
            ])
        except Exception:
            try:
                subprocess.Popen(['xterm', '-e', 'journalctl', '-u', 'lswitch', '-f'])
            except Exception as e:
                self.showMessage(
                    "Ошибка",
                    f"Не удалось открыть терминал.\nВыполните: journalctl -u lswitch -f",
                    QSystemTrayIcon.Warning,
                    5000
                )
    
    def on_tray_activated(self, reason):
        """Обработка клика по иконке в трее"""
        if reason == QSystemTrayIcon.Trigger:  # Левый клик - показываем статус
            status = self.get_service_status()
            if status == 'active':
                self.showMessage("LSwitch", "Служба работает ✅", QSystemTrayIcon.Information, 2000)
            else:
                self.showMessage("LSwitch", "Служба остановлена ⏸", QSystemTrayIcon.Warning, 2000)
        elif reason == QSystemTrayIcon.Context:  # Правый клик
            # Для CustomMenu показываем меню вручную
            if not self.adapter.supports_native_menu():
                self.menu.popup(QCursor.pos())
    
    def show_about(self):
        """Показывает информацию о программе"""
        de_info = f"DE: {self.de}, Display: {self.display_server}"
        adapter_info = f"Адаптер: {self.adapter.__class__.__name__}"
        
        self.showMessage(
            "LSwitch v1.0",
            f"Панель управления переключателем раскладки\n"
            f"Двойной Shift для переключения и конвертации текста\n\n"
            f"{de_info}\n"
            f"{adapter_info}\n\n"
            f"© 2026 Anton",
            QSystemTrayIcon.Information,
            5000
        )
    
    def quit_application(self):
        """Выход из панели управления (служба продолжит работать)"""
        QApplication.instance().quit()


def create_adaptive_icon():
    """Создает иконку, адаптированную к теме системы"""
    icon_path = os.path.join(os.path.dirname(__file__), 'lswitch.svg')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(os.path.dirname(__file__), 'lswitch.png')
    if not os.path.exists(icon_path):
        icon_path = '/usr/share/pixmaps/lswitch.svg'
    
    if os.path.exists(icon_path):
        icon = QIcon(icon_path)
    else:
        icon = QIcon.fromTheme('input-keyboard', QIcon.fromTheme('preferences-desktop-keyboard'))
    
    if icon.isNull():
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        palette = QApplication.instance().palette()
        text_color = palette.color(palette.WindowText)
        painter.setPen(text_color)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(8, 20, 48, 24, 4, 4)
        for row in range(2):
            for col in range(5):
                x = 12 + col * 8
                y = 24 + row * 8
                painter.fillRect(x, y, 6, 6, text_color)
        painter.end()
        icon = QIcon(pixmap)
    
    return icon


def main():
    """Главная функция"""
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
    
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # Устанавливаем стиль Fusion для кросс-платформенности
    app.setStyle('Fusion')
    
    # Определяем DE и адаптер до создания GUI
    de = detect_desktop_environment()
    print(f"Запуск на {de}", flush=True)
    
    icon = create_adaptive_icon()
    panel = LSwitchControlPanel(icon)
    panel.show()
    
    print("LSwitch Control Panel запущен", flush=True)
    panel.showMessage(
        "LSwitch",
        "Панель управления готова\nСлужба работает независимо",
        QSystemTrayIcon.Information,
        2000
    )
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
