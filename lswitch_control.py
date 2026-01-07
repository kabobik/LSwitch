#!/usr/bin/env python3
"""
LSwitch - GUI панель управления службой
Управляет systemd службой без запуска собственного процесса
"""

import sys
import os
import json
import signal
import subprocess
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtCore import Qt, QTimer


class LSwitchControlPanel(QSystemTrayIcon):
    """Панель управления службой LSwitch"""
    
    def __init__(self, icon, parent=None):
        super().__init__(icon, parent)
        
        self.config_path = self.find_config_path()
        self.config = self.load_config()
        
        # Создаем меню
        self.menu = QMenu()
        
        # Статус службы
        self.status_action = QAction("Статус: Проверка...", self.menu)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        
        self.menu.addSeparator()
        
        # Управление службой
        self.start_action = QAction("▶ Запустить службу", self.menu)
        self.start_action.triggered.connect(self.start_service)
        self.menu.addAction(self.start_action)
        
        self.stop_action = QAction("⏸ Остановить службу", self.menu)
        self.stop_action.triggered.connect(self.stop_service)
        self.menu.addAction(self.stop_action)
        
        self.restart_action = QAction("🔄 Перезапустить службу", self.menu)
        self.restart_action.triggered.connect(self.restart_service)
        self.menu.addAction(self.restart_action)
        
        self.menu.addSeparator()
        
        # Чекбокс для автопереключения
        self.auto_switch_action = QAction("Автопереключение", self.menu)
        self.auto_switch_action.setCheckable(True)
        self.auto_switch_action.setChecked(self.config.get('auto_switch', False))
        self.auto_switch_action.triggered.connect(self.toggle_auto_switch)
        self.menu.addAction(self.auto_switch_action)
        
        # Чекбокс для пользовательского словаря (самообучение)
        self.user_dict_action = QAction("📚 Самообучающийся словарь", self.menu)
        self.user_dict_action.setCheckable(True)
        self.user_dict_action.setChecked(self.config.get('user_dict_enabled', False))
        self.user_dict_action.triggered.connect(self.toggle_user_dict)
        self.menu.addAction(self.user_dict_action)
        
        self.menu.addSeparator()
        
        # Автозапуск службы
        self.autostart_action = QAction("Автозапуск при загрузке", self.menu)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.is_service_enabled())
        self.autostart_action.triggered.connect(self.toggle_autostart)
        self.menu.addAction(self.autostart_action)
        
        self.menu.addSeparator()
        
        # Логи
        logs_action = QAction("📋 Показать логи", self.menu)
        logs_action.triggered.connect(self.show_logs)
        self.menu.addAction(logs_action)
        
        # О программе
        about_action = QAction("О программе", self.menu)
        about_action.triggered.connect(self.show_about)
        self.menu.addAction(about_action)
        
        self.menu.addSeparator()
        
        # Выход (только из GUI, служба продолжит работать)
        exit_action = QAction("Выход из панели", self.menu)
        exit_action.triggered.connect(self.quit_application)
        self.menu.addAction(exit_action)
        
        self.setContextMenu(self.menu)
        
        # Обработка клика по иконке
        self.activated.connect(self.on_tray_activated)
        
        # Таймер для обновления статуса
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(2000)  # Каждые 2 секунды
        
        # Первое обновление
        self.update_status()
        
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
        """Сохраняет конфигурацию (может потребовать sudo)"""
        try:
            # Пробуем сохранить напрямую
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            print(f"Конфигурация сохранена: {self.config_path}", flush=True)
            return True
        except PermissionError:
            # Нужны права root - используем pkexec
            try:
                import tempfile
                # Создаем временный файл
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
                    json.dump(self.config, tmp, ensure_ascii=False, indent=2)
                    tmp_path = tmp.name
                
                # Копируем с правами root
                result = subprocess.run(
                    ['pkexec', 'cp', tmp_path, self.config_path],
                    capture_output=True, timeout=30
                )
                os.unlink(tmp_path)
                
                if result.returncode == 0:
                    print(f"Конфигурация сохранена через pkexec", flush=True)
                    return True
                else:
                    raise Exception("pkexec завершился с ошибкой")
            except Exception as e:
                print(f"Ошибка сохранения через pkexec: {e}", file=sys.stderr, flush=True)
                self.showMessage(
                    "Ошибка",
                    f"Не удалось сохранить настройки: {e}\n\nЗапустите: sudo chmod 666 {self.config_path}",
                    QSystemTrayIcon.Critical,
                    5000
                )
                return False
    
    def run_systemctl(self, action):
        """Выполняет команду systemctl"""
        try:
            # Пробуем через systemctl --user (если служба пользовательская)
            result = subprocess.run(
                ['systemctl', '--user', action, 'lswitch'],
                capture_output=True, timeout=5
            )
            
            if result.returncode != 0:
                # Пробуем системную службу через pkexec
                result = subprocess.run(
                    ['pkexec', 'systemctl', action, 'lswitch'],
                    capture_output=True, timeout=30
                )
            
            return result.returncode == 0
        except Exception as e:
            print(f"Ошибка выполнения systemctl {action}: {e}", file=sys.stderr, flush=True)
            return False
    
    def get_service_status(self):
        """Получает статус службы"""
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', 'lswitch'],
                capture_output=True, text=True, timeout=2
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"
    
    def is_service_enabled(self):
        """Проверяет включен ли автозапуск"""
        try:
            result = subprocess.run(
                ['systemctl', 'is-enabled', 'lswitch'],
                capture_output=True, text=True, timeout=2
            )
            return result.stdout.strip() == 'enabled'
        except Exception:
            return False
    
    def update_status(self):
        """Обновляет статус в меню"""
        status = self.get_service_status()
        
        if status == 'active':
            self.status_action.setText("Статус: ✅ Работает")
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(True)
            self.restart_action.setEnabled(True)
        elif status == 'inactive':
            self.status_action.setText("Статус: ⏸ Остановлен")
            self.start_action.setEnabled(True)
            self.stop_action.setEnabled(False)
            self.restart_action.setEnabled(False)
        else:
            self.status_action.setText("Статус: ❓ Неизвестно")
            self.start_action.setEnabled(True)
            self.stop_action.setEnabled(True)
            self.restart_action.setEnabled(True)
        
        # Обновляем чекбокс автозапуска
        self.autostart_action.setChecked(self.is_service_enabled())
    
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
        if reason == QSystemTrayIcon.Trigger:  # Левый клик
            self.contextMenu().popup(QApplication.instance().desktop().cursor().pos())
    
    def show_about(self):
        """Показывает информацию о программе"""
        self.showMessage(
            "LSwitch v1.0",
            "Панель управления переключателем раскладки\n"
            "Двойной Shift для переключения и конвертации текста\n\n"
            "Режим: GUI управляет systemd службой\n"
            "© 2026 Anton",
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
