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
import shutil
import importlib

from __version__ import __version__

import lswitch.system as _system_mod

# Adapter-level override for DI in tests
_control_system = None

def set_system(sys_impl):
    global _control_system
    _control_system = sys_impl


def get_system():
    if _control_system is not None:
        return _control_system
    return getattr(_system_mod, 'SYSTEM', _system_mod)

from PyQt5.QtWidgets import (QApplication, QSystemTrayIcon, QAction,
                             QMessageBox, QLabel)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette, QCursor, QFont
from PyQt5.QtCore import Qt, QTimer, QEvent, QPoint, QSize

# Импортируем локализацию
from lswitch.i18n import t, get_lang

# Импортируем адаптеры
from lswitch.adapters import get_adapter
from lswitch.utils.desktop import detect_desktop_environment, detect_display_server
import shutil


def get_system_scale_factor():
    """
    Получить коэффициент масштабирования из системы.
    Проверяет несколько источников:
    1. Переменные окружения Qt (QT_SCALE_FACTOR, QT_AUTO_SCREEN_SCALE_FACTOR)
    2. Переменные окружения GTK (GDK_SCALE, GDK_DPI_SCALE)
    3. GNOME текстовое масштабирование (text-scaling-factor)
    4. Физический DPI монитора
    """
    scale = 1.0
    
    try:
        # 1. Проверяем переменные окружения Qt
        qt_scale = os.environ.get('QT_SCALE_FACTOR')
        if qt_scale:
            try:
                scale = float(qt_scale)
                print(f"Найден QT_SCALE_FACTOR: {scale}", flush=True)
                return scale
            except ValueError:
                pass
        
        # 2. Проверяем GTK масштабирование
        gdk_scale = os.environ.get('GDK_SCALE')
        if gdk_scale:
            try:
                scale = float(gdk_scale)
                print(f"Найден GDK_SCALE: {scale}", flush=True)
                return scale
            except ValueError:
                pass
        
        gdk_dpi_scale = os.environ.get('GDK_DPI_SCALE')
        if gdk_dpi_scale:
            try:
                scale = float(gdk_dpi_scale)
                print(f"Найден GDK_DPI_SCALE: {scale}", flush=True)
                return scale
            except ValueError:
                pass
        
        # 3. Проверяем GNOME масштабирование шрифтов
        try:
            result = get_system().run(['gsettings', 'get', 'org.gnome.desktop.interface', 'text-scaling-factor'], capture_output=True, text=True, timeout=2)
            if getattr(result, 'returncode', 0) == 0:
                try:
                    gnome_scale = float(result.stdout.strip())
                    if gnome_scale != 1.0:
                        scale = gnome_scale
                        print(f"Найден GNOME text-scaling-factor: {scale}", flush=True)
                        return scale
                except Exception:
                    pass
        except Exception:
            pass
        
        # 4. Физический DPI экрана (проверяем через Qt)
        app = QApplication.instance()
        if app:
            screen = app.primaryScreen()
            if screen:
                logical_dpi = screen.logicalDotsPerInch()
                physical_dpi = screen.physicalDotsPerInch()
                
                # Сравниваем логический и физический DPI
                if physical_dpi > 0 and logical_dpi > 0:
                    dpi_scale = physical_dpi / logical_dpi
                    if abs(dpi_scale - 1.0) > 0.1:  # Если отличие > 10%
                        scale = dpi_scale
                        print(f"Рассчитан DPI масштаб (physical/logical): {physical_dpi}/{logical_dpi} = {scale:.2f}", flush=True)
                        return scale
                
                # Если масштаб не найден, используем логический DPI
                # (для HiDPI мониторов, где стандартный DPI не 96)
                if logical_dpi != 96:
                    scale = logical_dpi / 96.0
                    print(f"Рассчитан масштаб из логического DPI: {logical_dpi}/96 = {scale:.2f}", flush=True)
                    return scale
        
    except Exception as e:
        print(f"Ошибка при получении масштаба: {e}", flush=True)
    
    print(f"Используется стандартный масштаб: {scale}", flush=True)
    return max(1.0, scale)


def apply_scaling(app, scale_factor=None):
    """
    Применить масштабирование к приложению.
    """
    if scale_factor is None:
        scale_factor = get_system_scale_factor()
    
    # Информационный вывод
    if scale_factor > 1.0:
        app.setApplicationDisplayName(f"LSwitch Control (масштаб x{scale_factor:.2f})")
    
    print(f"Финальный коэффициент масштабирования: {scale_factor:.2f}", flush=True)
    return scale_factor


class LSwitchControlPanel(QSystemTrayIcon):
    """Панель управления в системном трее"""
    
    def __init__(self, icon, parent=None):
        # Some tests pass None as icon; create empty QIcon in that case
        from PyQt5.QtGui import QIcon
        if icon is None:
            icon = QIcon()
        super().__init__(icon, parent)
        
        # Определяем среду
        self.de = detect_desktop_environment()
        self.display_server = detect_display_server()
        print(f"Обнаружено: DE={self.de}, Display Server={self.display_server}", flush=True)
        
        # Получаем адаптер для текущего DE
        self.adapter = get_adapter()
        print(f"Используется адаптер: {self.adapter.__class__.__name__}", flush=True)
        
        # Загружаем конфигурацию через ConfigManager
        from lswitch.config import ConfigManager
        self.config_manager = ConfigManager()
        self.config = self.config_manager.get_all()

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
            print(t('using_custom_menu'), flush=True)
        else:
            print(t('using_native_menu'), flush=True)
        
        # Настройка шрифта меню (14 пикселей)
        menu_font = QFont()
        menu_font.setPointSize(14)
        self.menu.setFont(menu_font)
        
# Заголовок меню — недоступный для клика, информационный
        title_action = QAction(t('lswitch_control'), self)
        title_action.setEnabled(False)
        self.menu.addAction(title_action)
        self.menu.addSeparator()

        # Автопереключение (настоящий checkable action)
        self.auto_switch_action = QAction(t('auto_switch'), self)
        self.auto_switch_action.setCheckable(True)
        self.auto_switch_action.setChecked(self.auto_switch_checked)
        self.auto_switch_action.triggered.connect(self.toggle_auto_switch)
        self.menu.addAction(self.auto_switch_action)

        # Самообучающийся словарь (настоящий checkable action)
        self.user_dict_action = QAction(t('self_learning_dict'), self)
        self.user_dict_action.setCheckable(True)
        self.user_dict_action.setChecked(self.user_dict_checked)
        self.user_dict_action.triggered.connect(self.toggle_user_dict)
        self.menu.addAction(self.user_dict_action)

        # Автозапуск панели (локальный автозапуск GUI)
        self.gui_autostart_action = QAction("Автозапуск панели", self)
        self.gui_autostart_action.setCheckable(True)
        try:
            self.gui_autostart_action.setChecked(self.is_gui_autostart_enabled())
        except Exception:
            self.gui_autostart_action.setChecked(False)
        self.gui_autostart_action.triggered.connect(self.toggle_gui_autostart)
        self.menu.addAction(self.gui_autostart_action)
        
        self.menu.addSeparator()
        
        # --- Управление службой (плоское меню) ---
        
        # Статус службы
        self.status_action = QAction("Статус: " + self.get_service_status(), self)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        
        # Запустить
        self.start_action = QAction("Запустить", self)
        self.start_action.setIcon(QIcon.fromTheme("media-playback-start"))
        self.start_action.triggered.connect(self.start_service)
        self.menu.addAction(self.start_action)
        
        # Остановить
        self.stop_action = QAction("Остановить", self)
        self.stop_action.setIcon(QIcon.fromTheme("media-playback-stop"))
        self.stop_action.triggered.connect(self.stop_service)
        self.menu.addAction(self.stop_action)
        
        # Перезапустить
        self.restart_action = QAction("Перезапустить", self)
        self.restart_action.setIcon(QIcon.fromTheme("view-refresh"))
        self.restart_action.triggered.connect(self.restart_service)
        self.menu.addAction(self.restart_action)
        
        # Автозапуск службы
        self.autostart_action = QAction("Автозапуск службы", self)
        self.autostart_action.setCheckable(True)
        self.autostart_checked = self.is_service_enabled()
        self.autostart_action.setChecked(self.autostart_checked)
        self.autostart_action.triggered.connect(self.toggle_autostart)
        self.menu.addAction(self.autostart_action)

        # Добавляем разделитель после блока службы
        self.menu.addSeparator()
        
        self.menu.addSeparator()
        
        # Логи (скрыто)
        # logs_action = QAction("Показать логи", self)
        # logs_action.setIcon(QIcon.fromTheme("utilities-log-viewer"))
        # logs_action.triggered.connect(self.show_logs)
        # self.menu.addAction(logs_action)
        
        # О программе
        about_action = QAction(t('about'), self)
        about_action.setIcon(QIcon.fromTheme("help-about"))
        about_action.triggered.connect(self.show_about)
        self.menu.addAction(about_action)
        
        self.menu.addSeparator()
        
        # Выход
        quit_action = QAction(t('quit_panel'), self)
        quit_action.setIcon(QIcon.fromTheme("application-exit"))
        quit_action.triggered.connect(self.quit_application)
        self.menu.addAction(quit_action)
        
        # Для нативного QMenu устанавливаем контекстное меню
        if self.adapter.supports_native_menu():
            self.setContextMenu(self.menu)
        # Для CustomMenu обрабатываем правый клик вручную
    
    def load_config(self):
        """Load configuration using ConfigManager."""
        return self.config_manager.get_all()
    
    def save_config(self):
        """Save configuration using ConfigManager."""
        try:
            # Update config manager with current values
            self.config_manager.update(self.config)
            return self.config_manager.save()
        except Exception as e:
            print(f"Не удалось сохранить конфиг: {e}", file=sys.stderr, flush=True)
            return False
    
    def get_service_status(self):
        """Получает статус службы (проверяет systemctl и процессы)"""
        try:
            # Сначала проверяем systemctl
            result = get_system().run(['systemctl', '--user', 'is-active', 'lswitch'], capture_output=True, text=True, timeout=2)
            status = result.stdout.strip()
            if status == 'active':
                return 'active'
        except Exception:
            pass
        
        # Если systemctl не знает о демоне, проверяем процессы
        try:
            # Ищем процесс python3 -m lswitch
            result = get_system().run(['pgrep', '-f', '^python3 -m lswitch'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and result.stdout.strip():
                # Демон запущен вручную (вне systemctl)
                return 'active'
        except Exception:
            pass
        
        # Если оба способа не нашли демон
        return 'inactive'
    
    def update_service_status(self):
        """Обновляет отображение статуса службы в меню (делегирует в update_status)"""
        self.update_status()
    
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
        """Выполняет команду systemctl с защитой от дублей"""
        # Respect config toggle: allow GUI to manage service
        # Дополнительная защита для 'start': проверяем, не запущен ли уже демон
        if action == 'start':
            try:
                result = get_system().run(['pgrep', '-f', '^python3 -m lswitch'], capture_output=True, text=True, timeout=2)
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        self.showMessage("LSwitch", "Демон уже запущен! Остановите его перед повторным запуском.", QSystemTrayIcon.Warning, 3000)
                    except Exception:
                        pass
                    return False
            except Exception:
                pass

        try:
            get_system().run(['systemctl', '--user', action, 'lswitch'], check=True, timeout=10)
            return True
        except Exception as e:
            print(f"Ошибка systemctl {action}: {e}", file=sys.stderr, flush=True)
            try:
                self.showMessage(t('error'), t('failed_to_'+action), QSystemTrayIcon.Critical, 3000)
            except Exception:
                pass
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
                        print(t('detected_layouts', layouts=layouts), flush=True)
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


    




    def _start_user_gui(self, username):
        """Start the GUI in the session of the given username.

        Returns True on success, False otherwise.
        """
        import pwd
        try:
            pw = pwd.getpwnam(username)
            uid = pw.pw_uid
        except Exception:
            return False

        xdg_runtime = f"/run/user/{uid}"
        dbus_path = f"/run/user/{uid}/bus"

        env_parts = []
        if os.path.exists(xdg_runtime):
            env_parts.append(f"XDG_RUNTIME_DIR={xdg_runtime}")
        if os.path.exists(dbus_path):
            env_parts.append(f"DBUS_SESSION_BUS_ADDRESS=unix:path={dbus_path}")
        if 'DISPLAY' in os.environ:
            env_parts.append(f"DISPLAY={os.environ.get('DISPLAY')}")

        # Build sudo-based command to run command in user's session with env
        lsc_bin = shutil.which('lswitch-control') or 'lswitch-control'
        cmd = ['sudo', '-u', username, 'env'] + env_parts + [lsc_bin]
        try:
            system.Popen(cmd)
            return True
        except Exception:
            # fallback to su -c
            try:
                cmd2 = ['su', '-', username, '-c', f'{lsc_bin} &']
                system.Popen(cmd2)
                return True
            except Exception:
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
            result = system.setxkbmap_query(timeout=2)
            
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
                result2 = system.setxkbmap_query(timeout=2)
                
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
        """Обновляет состояние кнопок и статус в зависимости от статуса службы"""
        status = self.get_service_status()
        
        # Обновляем текст статуса в меню
        status_map = {
            'active': t('status_running'),
            'inactive': t('status_stopped'),
            'failed': t('status_error'),
            'unknown': t('status_unknown')
        }
        status_text = status_map.get(status, status)
        try:
            self.status_action.setText(f"{t('status')}: {status_text}")
        except Exception:
            pass
        
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
            self.showMessage("LSwitch", t('service_started'), QSystemTrayIcon.Information, 2000)
        else:
            # run_systemctl already shows a message if control is disabled or failed
            pass
        self.update_service_status()
    
    def stop_service(self):
        """Останавливает службу"""
        if self.run_systemctl('stop'):
            self.showMessage("LSwitch", t('service_stopped'), QSystemTrayIcon.Information, 2000)
        else:
            # run_systemctl already shows a message if control is disabled or failed
            pass
        self.update_service_status()
    
    def restart_service(self):
        """Перезапускает службу"""
        if self.run_systemctl('restart'):
            self.showMessage("LSwitch", t('service_restarted'), QSystemTrayIcon.Information, 2000)
        else:
            # run_systemctl already shows a message if control is disabled or failed
            pass
        self.update_service_status()
    
    def toggle_auto_switch(self):
        """Переключает режим автопереключения"""
        self.auto_switch_checked = not self.auto_switch_checked
        self.config['auto_switch'] = self.auto_switch_checked
        self.auto_switch_action.setChecked(self.auto_switch_checked)
        if self.save_config():
            # Отправляем сигнал службе для перезагрузки конфига
            self.reload_service_config()
            
            status_msg = t('auto_switch_enabled') if self.auto_switch_checked else t('auto_switch_disabled')
            self.showMessage(
                "LSwitch",
                status_msg,
                QSystemTrayIcon.Information,
                2000
            )
            # Если системный конфиг есть, но мы не записали туда изменения — предупредим пользователя

    def toggle_user_dict(self):
        """Переключает самообучающийся словарь"""
        self.user_dict_checked = not self.user_dict_checked
        self.config['user_dict_enabled'] = self.user_dict_checked
        self.user_dict_action.setChecked(self.user_dict_checked)
        if self.save_config():
            # Отправляем сигнал службе для перезагрузки конфига
            self.reload_service_config()
            
            status_msg = t('dict_enabled') if self.user_dict_checked else t('dict_disabled')
            self.showMessage(
                "LSwitch",
                status_msg,
                QSystemTrayIcon.Information,
                3000
            )



    def _system_autostart_present(self):
        """Return path to system-level autostart launcher if present, otherwise None."""
        candidates = [
            '/etc/xdg/autostart/lswitch-control.desktop',
            '/usr/share/applications/lswitch-control.desktop',
            '/usr/local/share/applications/lswitch-control.desktop'
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def is_gui_autostart_enabled(self):
        """Проверяет, установлен ли автозапуск панели для текущего пользователя или системой"""
        autostart_path = os.path.expanduser('~/.config/autostart/lswitch-control.desktop')
        return os.path.exists(autostart_path) or bool(self._system_autostart_present())

    def toggle_gui_autostart(self):
        """Включает/выключает автозапуск GUI панели (копирует .desktop в ~/.config/autostart)

        Ищет файл-источник в нескольких распространённых локациях и копирует первый найденный.
        """
        autostart_dir = os.path.expanduser('~/.config/autostart')
        autostart_file = os.path.join(autostart_dir, 'lswitch-control.desktop')
        # Возможные места, где может лежать системный .desktop
        candidates = [
            '/usr/share/applications/lswitch-control.desktop',
            '/usr/local/share/applications/lswitch-control.desktop',
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'lswitch-control.desktop'),
        ]
        try:
            os.makedirs(autostart_dir, exist_ok=True)
            if self.gui_autostart_action.isChecked():
                src = None
                for c in candidates:
                    if os.path.exists(c):
                        src = c
                        break
                if not src:
                    # Если исходный .desktop не найден — создаём минимальный .desktop в автозапуске
                    lsc_bin = shutil.which('lswitch-control') or 'lswitch-control'
                    content = f"""[Desktop Entry]
Type=Application
Exec={lsc_bin}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=LSwitcher
Comment=Control panel for LSwitch
"""
                    with open(autostart_file, 'w') as f:
                        f.write(content)
                else:
                    shutil.copy(src, autostart_file)

                # Попытка установить владельца файла текущего пользователя (на случай sudo запусков)
                try:
                    import pwd
                    uid = os.getuid()
                    gid = os.getgid()
                    os.chown(autostart_file, uid, gid)
                except Exception:
                    pass

                # After attempting to enable, read actual state and reflect it in the UI
                enabled = self.is_gui_autostart_enabled()
                try:
                    self.gui_autostart_action.setChecked(enabled)
                except Exception:
                    pass
                if enabled:
                    self.showMessage("LSwitch", t('autostart_enabled'), QSystemTrayIcon.Information, 2000)
                else:
                    self.showMessage("LSwitch", t('autostart_disabled'), QSystemTrayIcon.Information, 2000)
            else:
                # Block disabling up-front to avoid brief flicker when the checkbox is unchecked.
                sys_path = self._system_autostart_present()
                print(f"toggle_gui_autostart: disabling requested, local_exists={os.path.exists(autostart_file)}, system_path={sys_path}", flush=True)
                if sys_path:
                    try:
                        self.gui_autostart_action.setChecked(True)
                    except Exception:
                        pass
                    msg = t('autostart_managed_by_system', path=sys_path)
                    # Ensure system path is visible in message even if translation lookup failed
                    if sys_path and sys_path not in (msg or ''):
                        msg = f"Autostart is managed by the system ({sys_path}) and cannot be disabled here"
                    self.showMessage("LSwitch", msg, QSystemTrayIcon.Information, 4000)
                    return

                try:
                    os.remove(autostart_file)
                except FileNotFoundError:
                    pass
                # After attempting to disable, read actual state and reflect it in the UI
                enabled = self.is_gui_autostart_enabled()
                try:
                    self.gui_autostart_action.setChecked(enabled)
                except Exception:
                    pass
                if enabled:
                    self.showMessage("LSwitch", t('autostart_enabled'), QSystemTrayIcon.Information, 2000)
                else:
                    self.showMessage("LSwitch", t('autostart_disabled'), QSystemTrayIcon.Information, 2000)
        except Exception as e:
            print(f"Ошибка при изменении автозапуска GUI: {e}", file=sys.stderr, flush=True)
            # Откатываем чекбокс
            self.gui_autostart_action.setChecked(self.is_gui_autostart_enabled())
            self.showMessage(t('error'), t('failed_to_change_autostart'), QSystemTrayIcon.Critical, 3000)
    
    def reload_service_config(self):
        """Перезагружает конфигурацию службы без перезапуска"""
        try:
            # Сначала пробуем через systemctl (корректно целит unit для user/system служб)
            system.run(['systemctl', '--user', 'kill', '--signal=HUP', 'lswitch'], check=True, timeout=5)
            return
        except Exception:
            # Фолбэк: pkill по имени (подходит для /usr/local/bin/lswitch и других инсталляций)
            try:
                system.run(['pkill', '-HUP', '-f', 'lswitch'], timeout=2)
            except Exception as e:
                print(f"Не удалось отправить сигнал: {e}", file=sys.stderr, flush=True)
    
    def toggle_autostart(self):
        """Включает/выключает автозапуск службы"""
        self.autostart_checked = not self.autostart_checked
        action = 'enable' if self.autostart_checked else 'disable'
        if self.run_systemctl(action):
            status_msg = t('autostart_enabled') if self.autostart_checked else t('autostart_disabled')
            self.showMessage(
                "LSwitch",
                status_msg,
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
                t('error'),
                t('failed_to_change_autostart'),
                QSystemTrayIcon.Critical,
                3000
            )
    
    def show_logs(self):
        """Показывает логи в терминале"""
        try:
            system.Popen([
                'x-terminal-emulator', '-e',
                'journalctl', '--user', '-u', 'lswitch', '-f'
            ])
        except Exception:
            try:
                system.Popen(['xterm', '-e', 'journalctl', '--user', '-u', 'lswitch', '-f'])
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
            # Обновляем статус службы перед показом меню
            self.update_service_status()
            # Для CustomMenu показываем меню вручную
            if not self.adapter.supports_native_menu():
                self.menu.popup(QCursor.pos())
    
    def show_about(self):
        """Показывает информацию о программе"""
        de_info = t('about_de_info', de=self.de, display=self.display_server)
        adapter_info = t('about_adapter', adapter=self.adapter.__class__.__name__)
        
        self.showMessage(
            t('about_title', version=__version__),
            f"{t('about_description')}\\n\\n"
            f"{de_info}\\n"
            f"{adapter_info}\\n\\n"
            f"{t('about_copyright')}",
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
    
    # Устанавливаем атрибуты HiDPI ДО создания приложения
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # Применяем масштабирование из системы
    scale_factor = apply_scaling(app)
    
    # Устанавливаем стиль Fusion для кросс-платформенности
    app.setStyle('Fusion')
    
    # Определяем DE и адаптер до создания GUI
    de = detect_desktop_environment()
    print(f"Запуск на {de}", flush=True)
    
    icon = create_adaptive_icon()
    panel = LSwitchControlPanel(icon)
    panel.show()
    
    print(t('panel_started'), flush=True)
    panel.showMessage(
        "LSwitch",
        "Панель управления готова\nСлужба работает независимо",
        QSystemTrayIcon.Information,
        2000
    )
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
