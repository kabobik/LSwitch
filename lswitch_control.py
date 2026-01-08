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
from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, QAction, 
                             QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QCheckBox, QPushButton)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette, QCursor
from PyQt5.QtCore import Qt, QTimer, QEvent, pyqtSignal, QPoint


class CustomMenuItem(QWidget):
    """Кастомный пункт меню с темной темой"""
    clicked = pyqtSignal()
    
    def __init__(self, text, is_checkable=False, checked=False, bg_color=(46,46,51), fg_color=(255,255,255)):
        super().__init__()
        self.is_checkable = is_checkable
        self.checked = checked
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.hover_color = tuple(min(255, c + 20) for c in bg_color)
        self._enabled = True
        
        self.setMinimumHeight(48)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(18)
        
        if is_checkable:
            self.checkbox = QCheckBox()
            self.checkbox.setChecked(checked)
            self.checkbox.setStyleSheet(f"""
                QCheckBox {{
                    spacing: 0px;
                }}
                QCheckBox::indicator {{
                    width: 24px;
                    height: 24px;
                    border-radius: 4px;
                }}
                QCheckBox::indicator:checked {{
                    background-color: rgb(66, 133, 244);
                    border: none;
                }}
                QCheckBox::indicator:unchecked {{
                    background-color: rgba(60, 60, 65, 0.8);
                    border: 2px solid rgb(120, 120, 125);
                }}
                QCheckBox::indicator:hover:unchecked {{
                    border-color: rgb(150, 150, 155);
                    background-color: rgba(80, 80, 85, 0.8);
                }}
                QCheckBox::indicator:hover:checked {{
                    background-color: rgb(76, 143, 255);
                }}
            """)
            layout.addWidget(self.checkbox)
        
        self.label = QLabel(text)
        self.label.setStyleSheet(f"""
            color: rgb({fg_color[0]}, {fg_color[1]}, {fg_color[2]}); 
            background: transparent; 
            font-size: 24px;
            border: none;
            padding: 0;
        """)
        layout.addWidget(self.label)
        layout.addStretch()
        
        self.updateStyle(False)
    
    def setChecked(self, checked):
        if self.is_checkable:
            self.checked = checked
            self.checkbox.setChecked(checked)
    
    def isChecked(self):
        return self.checked if self.is_checkable else False
    
    def setEnabled(self, enabled):
        self._enabled = enabled
        if enabled:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.updateStyle(False)
    
    def updateStyle(self, hover):
        if not self._enabled:
            # Disabled style - серый текст
            color = self.bg_color
            text_color = "rgb(100, 100, 105)"
        else:
            color = self.hover_color if hover else self.bg_color
            text_color = f"rgb({self.fg_color[0]}, {self.fg_color[1]}, {self.fg_color[2]})"
        
        self.label.setStyleSheet(f"""
            color: {text_color}; 
            background: transparent; 
            font-size: 24px;
            border: none;
            padding: 0;
        """)
        
        # Чистый фон без обводок
        self.setStyleSheet(f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); border: none;")
    
    def enterEvent(self, event):
        if self._enabled:
            self.updateStyle(True)
    
    def leaveEvent(self, event):
        self.updateStyle(False)
    
    def mousePressEvent(self, event):
        if not self._enabled:
            return
        if self.is_checkable:
            self.checked = not self.checked
            self.checkbox.setChecked(self.checked)
        self.clicked.emit()


class CustomMenuSeparator(QWidget):
    """Разделитель для кастомного меню"""
    def __init__(self, color=(60,60,65)):
        super().__init__()
        self.setFixedHeight(1)
        self.setStyleSheet(f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); margin: 6px 10px;")


class CustomMenu(QWidget):
    """Кастомное темное меню вместо QMenu"""
    def __init__(self, bg_color=(46,46,51), fg_color=(255,255,255)):
        super().__init__()
        self.bg_color = bg_color
        self.fg_color = fg_color
        
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        
        border_color = tuple(min(255, c + 15) for c in bg_color)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
                border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});
                border-radius: 6px;
            }}
        """)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 8, 6, 8)
        self.layout.setSpacing(5)
        
        self.items = []
    
    def addItem(self, text, callback=None, checkable=False, checked=False):
        """Добавить пункт меню"""
        item = CustomMenuItem(text, checkable, checked, self.bg_color, self.fg_color)
        if callback:
            item.clicked.connect(callback)
        self.layout.addWidget(item)
        self.items.append(item)
        return item
    
    def addSeparator(self):
        """Добавить разделитель"""
        sep = CustomMenuSeparator(tuple(max(0, c - 10) for c in self.bg_color))
        self.layout.addWidget(sep)
    
    def popup(self, pos):
        """Показать меню в указанной позиции (выше курсора для трея)"""
        self.adjustSize()
        
        # Показываем меню ВЫШЕ курсора (для трея внизу экрана)
        # Сдвигаем на высоту меню + небольшой отступ
        menu_height = self.height()
        adjusted_pos = pos - QPoint(0, menu_height + 5)
        
        # Проверяем границы экрана
        from PyQt5.QtWidgets import QDesktopWidget
        screen = QDesktopWidget().screenGeometry()
        
        # Если меню выходит за верхнюю границу - показываем снизу
        if adjusted_pos.y() < 0:
            adjusted_pos = pos + QPoint(0, 5)
        
        # Если меню выходит за правую границу - сдвигаем влево
        if adjusted_pos.x() + self.width() > screen.width():
            adjusted_pos.setX(screen.width() - self.width() - 5)
        
        self.move(adjusted_pos)
        self.show()
        self.raise_()
        self.activateWindow()


class LSwitchControlPanel(QSystemTrayIcon):
    """Панель управления службой LSwitch"""
    
    def __init__(self, icon, parent=None):
        super().__init__(icon, parent)
        
        self.config_path = self.find_config_path()
        self.config = self.load_config()
        
        # Получаем цвета темы
        theme_colors = get_system_theme_colors()
        bg_color = theme_colors.get('bg_color', (46, 46, 51)) if theme_colors else (46, 46, 51)
        fg_color = theme_colors.get('fg_color', (255, 255, 255)) if theme_colors else (255, 255, 255)
        
        # Создаем КАСТОМНОЕ меню вместо QMenu
        self.menu = CustomMenu(bg_color, fg_color)
        
        # Статус службы
        self.status_item = self.menu.addItem("Статус: Проверка...")
        self.status_item.setCursor(Qt.ArrowCursor)
        
        self.menu.addSeparator()
        
        # Управление службой
        self.start_item = self.menu.addItem("▶ Запустить службу", self.start_service)
        self.stop_item = self.menu.addItem("■ Остановить службу", self.stop_service)
        self.restart_item = self.menu.addItem("⟳ Перезапустить службу", self.restart_service)
        
        self.menu.addSeparator()
        
        # Чекбоксы
        self.auto_switch_item = self.menu.addItem(
            "✓ Автопереключение", 
            self.toggle_auto_switch, 
            checkable=True, 
            checked=self.config.get('auto_switch', False)
        )
        
        self.user_dict_item = self.menu.addItem(
            "📚 Самообучающийся словарь", 
            self.toggle_user_dict,
            checkable=True,
            checked=self.config.get('user_dict_enabled', False)
        )
        
        self.menu.addSeparator()
        
        # Автозапуск службы
        self.autostart_item = self.menu.addItem(
            "⚡ Автозапуск при загрузке",
            self.toggle_autostart,
            checkable=True,
            checked=self.is_service_enabled()
        )
        
        self.menu.addSeparator()
        
        # Логи и информация
        self.menu.addItem("� Показать логи", self.show_logs)
        self.menu.addItem("ℹ О программе", self.show_about)
        
        self.menu.addSeparator()
        
        # Выход
        self.menu.addItem("⏻ Выход из панели", self.quit_application)
        
        # Обработка клика по иконке - показываем кастомное меню
        self.activated.connect(self.on_tray_activated)
        
        # Таймер для обновления статуса
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(2000)  # Каждые 2 секунды
        
        # Первое обновление
        self.update_status()
    
    def apply_menu_colors_immediately(self):
        """Применяет цвета темы к меню немедленно (вызывается при создании меню)"""
        theme_colors = get_system_theme_colors()
        
        if theme_colors and 'bg_color' in theme_colors:
            bg_rgb = theme_colors['bg_color']
            fg_rgb = theme_colors.get('fg_color', (255, 255, 255))
            
            # Применяем палитру к меню
            menu_palette = QPalette()
            menu_palette.setColor(QPalette.Window, QColor(*bg_rgb))
            menu_palette.setColor(QPalette.Base, QColor(*bg_rgb))
            menu_palette.setColor(QPalette.WindowText, QColor(*fg_rgb))
            menu_palette.setColor(QPalette.Text, QColor(*fg_rgb))
            menu_palette.setColor(QPalette.Button, QColor(*bg_rgb))
            menu_palette.setColor(QPalette.ButtonText, QColor(*fg_rgb))
            self.menu.setPalette(menu_palette)
            
            # Устанавливаем autoFillBackground для принудительного использования палитры
            self.menu.setAutoFillBackground(True)
            
            print(f"🎨 Цвета меню установлены сразу: bg=RGB{bg_rgb}, fg=RGB{fg_rgb}", flush=True)
    
    def apply_menu_style(self):
        """Применяет стилизацию меню с увеличенными отступами и цветами из темы"""
        # Получаем цвета системной темы
        theme_colors = get_system_theme_colors()
        
        # Применяем ТОЛЬКО палитру, без stylesheet (чтобы не конфликтовало)
        if theme_colors and 'bg_color' in theme_colors:
            menu_palette = QPalette()
            bg_rgb = theme_colors['bg_color']
            fg_rgb = theme_colors.get('fg_color', (255, 255, 255))
            base_rgb = theme_colors.get('base_color', bg_rgb)
            selected_rgb = theme_colors.get('selected_bg', (66, 133, 244))
            
            menu_palette.setColor(QPalette.Window, QColor(*bg_rgb))
            menu_palette.setColor(QPalette.WindowText, QColor(*fg_rgb))
            menu_palette.setColor(QPalette.Base, QColor(*base_rgb))
            menu_palette.setColor(QPalette.Button, QColor(*bg_rgb))
            menu_palette.setColor(QPalette.ButtonText, QColor(*fg_rgb))
            menu_palette.setColor(QPalette.Text, QColor(*fg_rgb))
            menu_palette.setColor(QPalette.Highlight, QColor(*selected_rgb))
            menu_palette.setColor(QPalette.HighlightedText, QColor(*fg_rgb))
            
            self.menu.setPalette(menu_palette)
            
            # Минимальный stylesheet только для отступов
            self.menu.setStyleSheet(f"""
                QMenu::item {{
                    padding: 10px 30px 10px 20px;
                    margin: 2px 4px;
                }}
                QMenu::separator {{
                    height: 1px;
                    margin: 6px 8px;
                }}
            """)
            
            print(f"✓ Применена палитра меню: bg=RGB{bg_rgb}, fg=RGB{fg_rgb}", flush=True)
        else:
            print(f"⚠️ Цвета темы не найдены, используем дефолт", flush=True)
        
        # Устанавливаем window flags для правильного поведения popup меню
        self.menu.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        
        # Добавляем атрибут для автоматического закрытия при потере фокуса
        self.menu.setAttribute(Qt.WA_X11NetWmWindowTypeMenu, True)
        
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
            self.status_item.label.setText("Статус: ✓ Работает")
            self.start_item.setEnabled(False)
            self.stop_item.setEnabled(True)
            self.restart_item.setEnabled(True)
        elif status == 'inactive':
            self.status_item.label.setText("Статус: ■ Остановлен")
            self.start_item.setEnabled(True)
            self.stop_item.setEnabled(False)
            self.restart_item.setEnabled(False)
        else:
            self.status_item.label.setText("Статус: ? Неизвестно")
            self.start_item.setEnabled(True)
            self.stop_item.setEnabled(True)
            self.restart_item.setEnabled(True)
        
        # Обновляем чекбокс автозапуска
        self.autostart_item.setChecked(self.is_service_enabled())
    
    def start_service(self):
        """Запускает службу"""
        self.menu.hide()
        if self.run_systemctl('start'):
            self.showMessage("LSwitch", "Служба запущена", QSystemTrayIcon.Information, 2000)
        else:
            self.showMessage("Ошибка", "Не удалось запустить службу", QSystemTrayIcon.Critical, 3000)
        self.update_status()
    
    def stop_service(self):
        """Останавливает службу"""
        self.menu.hide()
        if self.run_systemctl('stop'):
            self.showMessage("LSwitch", "Служба остановлена", QSystemTrayIcon.Information, 2000)
        else:
            self.showMessage("Ошибка", "Не удалось остановить службу", QSystemTrayIcon.Critical, 3000)
        self.update_status()
    
    def restart_service(self):
        """Перезапускает службу"""
        self.menu.hide()
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
        self.menu.hide()
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
            self.autostart_item.setChecked(checked)
        else:
            self.showMessage(
                "Ошибка",
                f"Не удалось изменить автозапуск",
                QSystemTrayIcon.Critical,
                3000
            )
            # Возвращаем чекбокс обратно
            self.autostart_item.setChecked(not checked)
    
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
        elif reason == QSystemTrayIcon.Context:  # Правый клик - показываем кастомное меню
            self.menu.popup(QCursor.pos())
    
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


def get_system_theme_colors():
    """
    Универсальная функция определения цветов темы для разных DE.
    Возвращает dict с цветами или None если не удалось определить.
    """
    import re
    
    def hex_to_rgb(hex_color):
        """Конвертирует #RRGGBB в (r, g, b)"""
        hex_color = hex_color.strip('#')
        if len(hex_color) == 6:
            return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))
        return None
    
    def parse_rgba(rgba_str):
        """Парсит rgba(r, g, b, a) в (r, g, b)"""
        match = re.search(r'rgba?\((\d+),\s*(\d+),\s*(\d+)', rgba_str)
        if match:
            return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        return None
    
    result = {'is_dark': False, 'theme_name': None}
    
    # Определяем DE и тему
    de = os.environ.get('DESKTOP_SESSION', '').lower()
    theme_name = None
    
    # 1. Cinnamon - читаем из cinnamon.css
    if 'cinnamon' in de:
        try:
            r = subprocess.run(['gsettings', 'get', 'org.cinnamon.theme', 'name'],
                             capture_output=True, text=True, timeout=1)
            if r.returncode == 0:
                theme_name = r.stdout.strip().strip("'\"")
                result['theme_name'] = theme_name
                result['is_dark'] = 'dark' in theme_name.lower()
                
                # Читаем GTK цвета (Cinnamon использует GTK темы для окон)
                for css_name in ['gtk-dark.css', 'gtk.css']:
                    css_file = f"/usr/share/themes/{theme_name}/gtk-3.0/{css_name}"
                    if os.path.exists(css_file):
                        with open(css_file, 'r') as f:
                            content = f.read()
                        
                        # Ищем @define-color theme_bg_color ...
                        bg_match = re.search(r'@define-color\s+theme_bg_color\s+([^;]+);', content)
                        if bg_match:
                            bg_value = bg_match.group(1).strip()
                            rgb = hex_to_rgb(bg_value)
                            if rgb:
                                result['bg_color'] = rgb
                        
                        # Ищем @define-color theme_fg_color ...
                        fg_match = re.search(r'@define-color\s+theme_fg_color\s+([^;]+);', content)
                        if fg_match:
                            fg_value = fg_match.group(1).strip()
                            rgb = hex_to_rgb(fg_value) or parse_rgba(fg_value)
                            if rgb:
                                result['fg_color'] = rgb
                        
                        # Ищем @define-color theme_base_color ...
                        base_match = re.search(r'@define-color\s+theme_base_color\s+([^;]+);', content)
                        if base_match:
                            base_value = base_match.group(1).strip()
                            rgb = hex_to_rgb(base_value)
                            if rgb:
                                result['base_color'] = rgb
                        
                        # Ищем @define-color theme_selected_bg_color ...
                        sel_match = re.search(r'@define-color\s+theme_selected_bg_color\s+([^;]+);', content)
                        if sel_match:
                            sel_value = sel_match.group(1).strip()
                            rgb = hex_to_rgb(sel_value)
                            if rgb:
                                result['selected_bg'] = rgb
                        
                        if result.get('bg_color'):
                            print(f"✓ Cinnamon theme: {theme_name} ({'темная' if result['is_dark'] else 'светлая'})", flush=True)
                            return result
        except Exception as e:
            print(f"⚠️ Ошибка чтения Cinnamon темы: {e}", flush=True)
    
    # 2. GNOME/GTK - читаем из gtk.css
    try:
        r = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-theme'],
                         capture_output=True, text=True, timeout=1)
        if r.returncode == 0:
            theme_name = r.stdout.strip().strip("'\"")
            result['theme_name'] = theme_name
            result['is_dark'] = 'dark' in theme_name.lower()
            
            # Читаем цвета из gtk-3.0/gtk.css или gtk-dark.css
            for css_name in ['gtk-dark.css', 'gtk.css']:
                css_file = f"/usr/share/themes/{theme_name}/gtk-3.0/{css_name}"
                if os.path.exists(css_file):
                    with open(css_file, 'r') as f:
                        content = f.read()
                    
                    # Ищем @define-color theme_bg_color ...
                    bg_match = re.search(r'@define-color\s+theme_bg_color\s+([^;]+);', content)
                    if bg_match:
                        bg_value = bg_match.group(1).strip()
                        rgb = hex_to_rgb(bg_value)
                        if rgb:
                            result['bg_color'] = rgb
                    
                    # Ищем @define-color theme_fg_color ...
                    fg_match = re.search(r'@define-color\s+theme_fg_color\s+([^;]+);', content)
                    if fg_match:
                        fg_value = fg_match.group(1).strip()
                        rgb = hex_to_rgb(fg_value)
                        if rgb:
                            result['fg_color'] = rgb
                    
                    # Ищем @define-color theme_base_color ...
                    base_match = re.search(r'@define-color\s+theme_base_color\s+([^;]+);', content)
                    if base_match:
                        base_value = base_match.group(1).strip()
                        rgb = hex_to_rgb(base_value)
                        if rgb:
                            result['base_color'] = rgb
                    
                    # Ищем @define-color theme_selected_bg_color ...
                    sel_match = re.search(r'@define-color\s+theme_selected_bg_color\s+([^;]+);', content)
                    if sel_match:
                        sel_value = sel_match.group(1).strip()
                        rgb = hex_to_rgb(sel_value)
                        if rgb:
                            result['selected_bg'] = rgb
                    
                    if result.get('bg_color'):
                        print(f"✓ GTK theme: {theme_name} ({'темная' if result['is_dark'] else 'светлая'})", flush=True)
                        return result
    except Exception as e:
        print(f"⚠️ Ошибка чтения GTK темы: {e}", flush=True)
    
    # 3. Fallback - только проверка названия темы
    if result.get('is_dark'):
        print(f"✓ Тема {theme_name} определена как темная (по названию)", flush=True)
        # Используем дефолтные темные цвета
        result['bg_color'] = (53, 53, 53)
        result['fg_color'] = (255, 255, 255)
        result['base_color'] = (35, 35, 35)
        result['selected_bg'] = (42, 130, 218)
        return result
    
    return None


def main():
    """Главная функция"""
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
    sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
    
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    
    # КРИТИЧНО: Получаем цвета темы ДО создания QApplication
    theme_colors = get_system_theme_colors()
    
    # Устанавливаем переменную окружения для Qt
    if theme_colors and theme_colors.get('is_dark'):
        os.environ['QT_QPA_PLATFORMTHEME'] = 'gtk3'
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # КРИТИЧНО: Устанавливаем стиль Fusion для кросс-платформенной темизации
    app.setStyle('Fusion')
    
    # Применяем цвета темы
    if theme_colors and theme_colors.get('is_dark'):
        try:
            from PyQt5.QtGui import QPalette, QColor
            dark_palette = QPalette()
            
            # Используем РЕАЛЬНЫЕ цвета из темы
            bg_color = theme_colors.get('bg_color', (53, 53, 53))
            fg_color = theme_colors.get('fg_color', (255, 255, 255))
            base_color = theme_colors.get('base_color', (35, 35, 35))
            selected_bg = theme_colors.get('selected_bg', (42, 130, 218))
            
            # Применяем темную палитру ко всем элементам
            dark_palette.setColor(QPalette.Window, QColor(*bg_color))
            dark_palette.setColor(QPalette.WindowText, QColor(*fg_color))
            dark_palette.setColor(QPalette.Base, QColor(*base_color))
            dark_palette.setColor(QPalette.AlternateBase, QColor(*bg_color))
            dark_palette.setColor(QPalette.ToolTipBase, QColor(*base_color))
            dark_palette.setColor(QPalette.ToolTipText, QColor(*fg_color))
            dark_palette.setColor(QPalette.Text, QColor(*fg_color))
            dark_palette.setColor(QPalette.Button, QColor(*bg_color))
            dark_palette.setColor(QPalette.ButtonText, QColor(*fg_color))
            dark_palette.setColor(QPalette.BrightText, QColor(*fg_color))
            dark_palette.setColor(QPalette.Link, QColor(*selected_bg))
            dark_palette.setColor(QPalette.Highlight, QColor(*selected_bg))
            dark_palette.setColor(QPalette.HighlightedText, QColor(*fg_color))
            app.setPalette(dark_palette)
            
            # КРИТИЧНО: Также применяем глобальный stylesheet для принудительной темизации меню
            bg_str = f"rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]})"
            fg_str = f"rgb({fg_color[0]}, {fg_color[1]}, {fg_color[2]})"
            hover_rgb = tuple(min(255, c + 20) for c in bg_color)
            hover_str = f"rgb({hover_rgb[0]}, {hover_rgb[1]}, {hover_rgb[2]})"
            
            app.setStyleSheet(f"""
                QMenu {{
                    background-color: {bg_str};
                    color: {fg_str};
                    border: 1px solid {hover_str};
                }}
                QMenu::item {{
                    padding: 10px 30px 10px 20px;
                    background-color: transparent;
                }}
                QMenu::item:selected {{
                    background-color: {hover_str};
                }}
                QMenu::separator {{
                    height: 1px;
                    background: {hover_str};
                    margin: 6px 8px;
                }}
            """)
            
            theme_name = theme_colors.get('theme_name', 'Unknown')
            print(f"✓ Применены цвета темы {theme_name}", flush=True)
            print(f"  Фон: RGB{bg_color}, Текст: RGB{fg_color}", flush=True)
            print(f"  Global stylesheet: {bg_str}", flush=True)
        except Exception as e:
            print(f"⚠️ Ошибка применения темы: {e}", flush=True)
    
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
