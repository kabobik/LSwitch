#!/usr/bin/env python3
"""
LSwitch - GUI панель управления службой
Управляет systemd службой без запуска собственного процесса
Модульная версия с адаптерами под разные DE
"""

import sys
import os
import json
import time
import signal
import subprocess
import time
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QAction,
                             QMessageBox, QLabel)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette, QCursor
from PyQt5.QtCore import Qt, QTimer, QEvent, QPoint, QSize

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
        
        # Состояние чекбоксов
        self.auto_switch_checked = self.config.get('auto_switch', True)
        self.user_dict_checked = self.config.get('user_dict_enabled', False)
        self.autostart_checked = False  # Будет обновлено в create_tray_menu
        
        # Создаём меню через адаптер
        self.create_tray_menu()
        
        # Обработка клика по иконке
        self.activated.connect(self.on_tray_activated)
        
        # Обновляем статус службы
        self.update_status()
        
        # Публикуем текущие раскладки для демона
        self.last_published_layouts = []
        self.layout_change_history = []  # История изменений для защиты от глюков KDE
        self.publish_layouts()
        
        # Таймер для обновления статуса службы и редких проверок раскладок
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(30000)  # Каждые 30 секунд - статус службы
        
        # Отдельный таймер для проверки раскладок - РЕДКО, чтобы не триггерить баг KDE
        self.layout_timer = QTimer()
        self.layout_timer.timeout.connect(self.check_and_publish_layouts)
        self.layout_timer.start(300000)  # Каждые 5 минут (редко = меньше глюков)
    
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
        title_action = QAction("LSwitch Control", self)
        title_action.setEnabled(False)
        self.menu.addAction(title_action)
        self.menu.addSeparator()
        
        # Управление службой (для Cinnamon без вложенного меню)
        if self.de == 'cinnamon':
            self.start_action = QAction("Запустить", self)
            self.start_action.setIcon(QIcon.fromTheme("media-playback-start"))
            self.start_action.triggered.connect(self.start_service)
            self.menu.addAction(self.start_action)
            
            self.stop_action = QAction("Остановить", self)
            self.stop_action.setIcon(QIcon.fromTheme("media-playback-stop"))
            self.stop_action.triggered.connect(self.stop_service)
            self.menu.addAction(self.stop_action)
            
            self.restart_action = QAction("Перезапустить", self)
            self.restart_action.setIcon(QIcon.fromTheme("view-refresh"))
            self.restart_action.triggered.connect(self.restart_service)
            self.menu.addAction(self.restart_action)
            
            self.menu.addSeparator()
        else:
            # Вложенное меню для KDE и других DE
            from PyQt5.QtWidgets import QMenu as QtMenu
            service_menu = QtMenu("Управление службой", self)
            service_menu.setIcon(QIcon.fromTheme("preferences-system"))
            
            self.start_action = QAction("Запустить", service_menu)
            self.start_action.setIcon(QIcon.fromTheme("media-playback-start"))
            self.start_action.triggered.connect(self.start_service)
            service_menu.addAction(self.start_action)
            
            self.stop_action = QAction("Остановить", service_menu)
            self.stop_action.setIcon(QIcon.fromTheme("media-playback-stop"))
            self.stop_action.triggered.connect(self.stop_service)
            service_menu.addAction(self.stop_action)
            
            self.restart_action = QAction("Перезапустить", service_menu)
            self.restart_action.setIcon(QIcon.fromTheme("view-refresh"))
            self.restart_action.triggered.connect(self.restart_service)
            service_menu.addAction(self.restart_action)
            
            self.menu.addMenu(service_menu)
            self.menu.addSeparator()
        
        # Автопереключение (настоящий checkable action)
        self.auto_switch_action = QAction("Автопереключение", self)
        self.auto_switch_action.setCheckable(True)
        self.auto_switch_action.setChecked(self.auto_switch_checked)
        self.auto_switch_action.triggered.connect(self.toggle_auto_switch)
        self.menu.addAction(self.auto_switch_action)
        
        # Самообучающийся словарь (настоящий checkable action)
        self.user_dict_action = QAction("Самообучающийся словарь", self)
        self.user_dict_action.setCheckable(True)
        self.user_dict_action.setChecked(self.user_dict_checked)
        self.user_dict_action.triggered.connect(self.toggle_user_dict)
        self.menu.addAction(self.user_dict_action)
        
        # Автозапуск (настоящий checkable action)
        self.autostart_action = QAction("Автозапуск службы", self)
        self.autostart_action.setCheckable(True)
        self.autostart_checked = self.is_service_enabled()
        self.autostart_action.setChecked(self.autostart_checked)
        self.autostart_action.triggered.connect(self.toggle_autostart)
        self.menu.addAction(self.autostart_action)
        
        self.menu.addSeparator()
        
        # Логи
        logs_action = QAction("Показать логи", self)
        logs_action.setIcon(QIcon.fromTheme("utilities-log-viewer"))
        logs_action.triggered.connect(self.show_logs)
        self.menu.addAction(logs_action)
        
        # О программе
        about_action = QAction("О программе", self)
        about_action.setIcon(QIcon.fromTheme("help-about"))
        about_action.triggered.connect(self.show_about)
        self.menu.addAction(about_action)
        
        self.menu.addSeparator()
        
        # Выход
        quit_action = QAction("Выход из панели", self)
        quit_action.setIcon(QIcon.fromTheme("application-exit"))
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
    
    def publish_layouts(self):
        """Публикует текущие раскладки в файл для демона"""
        try:
            layouts = []
            
            # Приоритет 1: Читаем из конфига KDE (стабильно, не подвержено багам)
            kde_config = os.path.expanduser('~/.config/kxkbrc')
            if os.path.exists(kde_config):
                try:
                    import configparser
                    config = configparser.ConfigParser()
                    config.read(kde_config)
                    if 'Layout' in config and 'LayoutList' in config['Layout']:
                        layout_list = config['Layout']['LayoutList']
                        layouts = [l.strip() for l in layout_list.split(',')]
                        # Нормализуем us -> en
                        layouts = ['en' if l == 'us' else l for l in layouts if l]
                        print(f"✓ Раскладки из конфига KDE: {layouts}", flush=True)
                except Exception as e:
                    print(f"⚠️  Ошибка чтения kxkbrc: {e}", flush=True)
            
            # Fallback: setxkbmap (может глючить в KDE, но работает в других DE)
            if not layouts:
                result = subprocess.run(
                    ['setxkbmap', '-query'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                for line in result.stdout.split('\n'):
                    if line.startswith('layout:'):
                        layouts_str = line.split(':', 1)[1].strip()
                        layouts = [l.strip() for l in layouts_str.split(',')]
                        # Нормализуем us -> en
                        layouts = ['en' if l == 'us' else l for l in layouts if l]
                        print(f"✓ Раскладки из setxkbmap: {layouts}", flush=True)
                        break
            
            # ВАЛИДАЦИЯ: НЕ публикуем если меньше 2 раскладок
            if len(layouts) < 2:
                print(f"⚠️  Игнорируем некорректные раскладки: {layouts} (ожидается >= 2)", flush=True)
                return False
            
            if layouts:
                # Пишем в runtime файл
                runtime_dir = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
                layouts_file = f'{runtime_dir}/lswitch_layouts.json'
                
                import time
                with open(layouts_file, 'w') as f:
                    json.dump({
                        'layouts': layouts, 
                        'timestamp': int(time.time())
                    }, f)
                
                self.last_published_layouts = layouts
                return True
                    
        except Exception as e:
            print(f"Ошибка публикации раскладок: {e}", file=sys.stderr, flush=True)
            return False
    
    def check_and_publish_layouts(self):
        """Проверяет и публикует раскладки только при изменении (с защитой от глюков KDE)"""
        try:
            # Очищаем историю старше 60 секунд
            current_time = time.time()
            self.layout_change_history = [
                t for t in self.layout_change_history 
                if current_time - t < 60
            ]
            
            # Читаем текущие раскладки
            result = subprocess.run(
                ['setxkbmap', '-query'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            current_layouts = []
            for line in result.stdout.split('\n'):
                if line.startswith('layout:'):
                    layouts_str = line.split(':', 1)[1].strip()
                    current_layouts = [l.strip() for l in layouts_str.split(',')]
                    current_layouts = ['en' if l == 'us' else l for l in current_layouts if l]
                    break
            
            # Публикуем только если изменились
            if current_layouts and current_layouts != self.last_published_layouts:
                # Проверяем: не слишком ли часто меняются?
                if len(self.layout_change_history) >= 3:
                    print(f"⚠️  KDE глючит - слишком частые изменения раскладок (игнорируем)", flush=True)
                    return
                
                # KDE Plasma глючит - двойная проверка через 0.5 сек
                time.sleep(0.5)
                
                # Повторная проверка
                result2 = subprocess.run(
                    ['setxkbmap', '-query'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                current_layouts2 = []
                for line in result2.stdout.split('\n'):
                    if line.startswith('layout:'):
                        layouts_str = line.split(':', 1)[1].strip()
                        current_layouts2 = [l.strip() for l in layouts_str.split(',')]
                        current_layouts2 = ['en' if l == 'us' else l for l in current_layouts2 if l]
                        break
                
                # Публикуем только если оба раза одинаково
                if current_layouts == current_layouts2:
                    print(f"Раскладки изменились: {self.last_published_layouts} → {current_layouts}", flush=True)
                    self.layout_change_history.append(current_time)
                    self.publish_layouts()
                else:
                    print(f"⚠️  KDE глюк проигнорирован: {current_layouts} != {current_layouts2}", flush=True)
                
        except Exception as e:
            print(f"Ошибка проверки раскладок: {e}", file=sys.stderr, flush=True)
    
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
    
    def toggle_auto_switch(self):
        """Переключает режим автопереключения"""
        self.auto_switch_checked = not self.auto_switch_checked
        self.config['auto_switch'] = self.auto_switch_checked
        self.auto_switch_action.setChecked(self.auto_switch_checked)
        if self.save_config():
            # Отправляем сигнал службе для перезагрузки конфига
            self.reload_service_config()
            
            status = "включено" if self.auto_switch_checked else "выключено"
            self.showMessage(
                "LSwitch",
                f"Автопереключение {status}",
                QSystemTrayIcon.Information,
                2000
            )
    
    def toggle_user_dict(self):
        """Переключает самообучающийся словарь"""
        self.user_dict_checked = not self.user_dict_checked
        self.config['user_dict_enabled'] = self.user_dict_checked
        self.user_dict_action.setChecked(self.user_dict_checked)
        if self.save_config():
            # Отправляем сигнал службе для перезагрузки конфига
            self.reload_service_config()
            
            status = "включён" if self.user_dict_checked else "выключен"
            msg = f"Самообучающийся словарь {status}"
            if self.user_dict_checked:
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
    
    def toggle_autostart(self):
        """Включает/выключает автозапуск службы"""
        self.autostart_checked = not self.autostart_checked
        action = 'enable' if self.autostart_checked else 'disable'
        if self.run_systemctl(action):
            status = "включен" if self.autostart_checked else "выключен"
            self.showMessage(
                "LSwitch",
                f"Автозапуск {status}",
                QSystemTrayIcon.Information,
                2000
            )
            # Обновляем состояние чекбокса
            self.autostart_action.setChecked(self.autostart_checked)
        else:
            # Откатываем изменение
            self.autostart_checked = not self.autostart_checked
            self.autostart_action.setChecked(self.autostart_checked)
            self.showMessage(
                "Ошибка",
                f"Не удалось изменить автозапуск",
                QSystemTrayIcon.Critical,
                3000
            )
    
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
        if reason == QSystemTrayIcon.Context:  # Правый клик - показываем меню
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


def create_adaptive_icon():
    """Создает упрощенную иконку для системного трея"""
    # Создаем два варианта иконки - для светлой и темной темы
    icon = QIcon()
    
    # Белая иконка для тёмной темы (Normal/Active)
    light_pixmap = create_simple_icon(QColor(255, 255, 255))
    icon.addPixmap(light_pixmap, QIcon.Normal)
    icon.addPixmap(light_pixmap, QIcon.Active)
    
    # Тёмная иконка для светлой темы (Disabled/Selected)
    dark_pixmap = create_simple_icon(QColor(50, 50, 50))
    icon.addPixmap(dark_pixmap, QIcon.Disabled)
    icon.addPixmap(dark_pixmap, QIcon.Selected)
    
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
