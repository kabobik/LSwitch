"""Модуль локализации для LSwitch 2.0.

Автоматически определяет язык системы и предоставляет переводы.
Чистый Python, 0 внешних зависимостей.
"""

from __future__ import annotations

import os
import locale


class I18n:
    """Класс для управления локализацией."""

    def __init__(self):
        self.lang = self._detect_language()
        self._translations = self._load_translations()

    def _detect_language(self) -> str:
        """Определяет язык системы."""
        try:
            lang = os.environ.get('LANG', '')
            if lang:
                return 'ru' if lang.startswith('ru') else 'en'

            system_locale = locale.getlocale()[0]
            if system_locale and system_locale.startswith('ru'):
                return 'ru'
        except Exception:
            pass

        return 'en'

    def _load_translations(self) -> dict[str, dict[str, str]]:
        """Загружает переводы для всех языков."""
        return {
            'en': {
                # Menu items
                'lswitch_control': 'LSwitch Control',
                'auto_switch': 'Auto-switch',
                'auto_switch_threshold': 'N-gram sensitivity',
                'auto_switch_threshold_title': 'Auto-switch sensitivity',
                'auto_switch_threshold_prompt': 'Threshold (higher = fewer auto-switches)',
                'self_learning_dict': 'Self-learning Dictionary',
                'service_management': 'Service Management',
                'status': 'Status',
                'start': 'Start',
                'stop': 'Stop',
                'restart': 'Restart',
                'service_autostart': 'Service Autostart',
                'show_logs': 'Show Logs',
                'about': 'About',
                'quit_panel': 'Quit Panel',

                # Status messages
                'status_running': 'Running',
                'status_stopped': 'Stopped',
                'status_error': 'Error',
                'status_unknown': 'Unknown',

                # Service messages
                'service_started': 'Service started',
                'service_stopped': 'Service stopped',
                'service_restarted': 'Service restarted',
                'error': 'Error',
                'failed_to_start': 'Failed to start service',
                'failed_to_stop': 'Failed to stop service',
                'failed_to_restart': 'Failed to restart service',

                # Auto-switch messages
                'auto_switch_enabled': 'Auto-switch enabled',
                'auto_switch_disabled': 'Auto-switch disabled',

                # Dictionary messages
                'dict_enabled': 'Self-learning dictionary enabled',
                'dict_disabled': 'Self-learning dictionary disabled',

                # Autostart messages
                'autostart_enabled': 'Autostart enabled',
                'autostart_disabled': 'Autostart disabled',
                'failed_to_change_autostart': 'Failed to change autostart',
                'autostart_managed_by_system': 'Autostart is managed by the system ({path}) and cannot be disabled here',
                'config_save_error': 'Failed to save settings',

                # About dialog
                'about_title': 'LSwitch v{version}',
                'about_description': 'Layout switcher control panel\nDouble Shift to switch and convert text',
                'about_de_info': 'DE: {de}, Display: {display}',
                'about_adapter': 'Adapter: {adapter}',
                'about_copyright': '© 2026 Anton',

                # Console messages
                'using_custom_menu': 'Using custom menu (CustomMenu)',
                'using_native_menu': 'Using native QMenu',
                'detected_layouts': '✓ Layouts from KDE config: {layouts}',
                'panel_started': 'LSwitch Control Panel started',

                # Config dialog
                'double_click_timeout': 'Double click timeout',
                'reset_defaults': 'Reset defaults',
            },
            'ru': {
                # Пункты меню
                'lswitch_control': 'Управление LSwitch',
                'auto_switch': 'Автопереключение',
                'auto_switch_threshold': 'Чувствительность n-грамм',
                'auto_switch_threshold_title': 'Чувствительность автопереключения',
                'auto_switch_threshold_prompt': 'Порог (выше = меньше автопереключений)',
                'self_learning_dict': 'Самообучающийся словарь',
                'service_management': 'Управление службой',
                'status': 'Статус',
                'start': 'Запустить',
                'stop': 'Остановить',
                'restart': 'Перезапустить',
                'service_autostart': 'Автозапуск службы',
                'show_logs': 'Показать логи',
                'about': 'О программе',
                'quit_panel': 'Выход из панели',

                # Статусы
                'status_running': 'Запущен',
                'status_stopped': 'Остановлен',
                'status_error': 'Ошибка',
                'status_unknown': 'Неизвестно',

                # Сообщения службы
                'service_started': 'Служба запущена',
                'service_stopped': 'Служба остановлена',
                'service_restarted': 'Служба перезапущена',
                'error': 'Ошибка',
                'failed_to_start': 'Не удалось запустить службу',
                'failed_to_stop': 'Не удалось остановить службу',
                'failed_to_restart': 'Не удалось перезапустить службу',

                # Сообщения автопереключения
                'auto_switch_enabled': 'Автопереключение включено',
                'auto_switch_disabled': 'Автопереключение выключено',

                # Сообщения словаря
                'dict_enabled': 'Самообучающийся словарь включен',
                'dict_disabled': 'Самообучающийся словарь выключен',

                # Сообщения автозапуска
                'autostart_enabled': 'Автозапуск включен',
                'autostart_disabled': 'Автозапуск выключен',
                'failed_to_change_autostart': 'Не удалось изменить автозапуск',
                'autostart_managed_by_system': 'Автозапуск управляется системой ({path}) и не может быть отключён здесь',
                'config_save_error': 'Не удалось сохранить настройки',

                # Диалог О программе
                'about_title': 'LSwitch v{version}',
                'about_description': 'Панель управления переключателем раскладки\nДвойной Shift для переключения и конвертации текста',
                'about_de_info': 'DE: {de}, Display: {display}',
                'about_adapter': 'Адаптер: {adapter}',
                'about_copyright': '© 2026 Anton',

                # Консольные сообщения
                'using_custom_menu': 'Используется кастомное меню (CustomMenu)',
                'using_native_menu': 'Используется нативное QMenu',
                'detected_layouts': '✓ Раскладки из конфига KDE: {layouts}',
                'panel_started': 'Панель управления LSwitch запущена',

                # Config dialog
                'double_click_timeout': 'Таймаут двойного клика',
                'reset_defaults': 'Сбросить настройки',
            },
        }

    def t(self, key: str, **kwargs) -> str:
        """Возвращает перевод для ключа с подстановкой параметров."""
        lang_map = self._translations.get(self.lang, self._translations.get('en', {}))
        text = lang_map.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text

    def get_lang(self) -> str:
        """Возвращает текущий язык."""
        return self.lang


# Глобальный экземпляр для использования в приложении
_i18n = I18n()


def t(key: str, **kwargs) -> str:
    """Глобальная функция перевода."""
    return _i18n.t(key, **kwargs)


def get_lang() -> str:
    """Возвращает текущий язык."""
    return _i18n.get_lang()
