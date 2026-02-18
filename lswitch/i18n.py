#!/usr/bin/env python3
"""
Модуль локализации для LSwitch
Автоматически определяет язык системы и предоставляет переводы
"""

import os
import locale


class I18n:
    """Класс для управления локализацией"""
    
    def __init__(self):
        self.lang = self._detect_language()
        self.translations = self._load_translations()
    
    def _detect_language(self):
        """Определяет язык системы"""
        try:
            # Пробуем получить из переменных окружения
            lang = os.environ.get('LANG', '')
            if lang.startswith('ru'):
                return 'ru'
            
            # Пробуем через locale
            system_locale = locale.getdefaultlocale()[0]
            if system_locale and system_locale.startswith('ru'):
                return 'ru'
        except:
            pass
        
        # По умолчанию английский
        return 'en'
    
    def _load_translations(self):
        """Загружает переводы для выбранного языка"""
        translations = {
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
                
            }
        }
        
        return translations.get(self.lang, translations['en'])
    
    def t(self, key, **kwargs):
        """Возвращает перевод для ключа с подстановкой параметров"""
        # Support two shapes of self.translations:
        # 1) full mapping {'en': {...}, 'ru': {...}}
        # 2) already selected language mapping { 'lswitch_control': '...' }
        if isinstance(self.translations, dict) and 'en' in self.translations and 'ru' in self.translations:
            lang_map = self.translations.get(self.lang, self.translations.get('en', {}))
        else:
            lang_map = self.translations or {}
        text = lang_map.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                return text
        return text
    
    def get_lang(self):
        """Возвращает текущий язык"""
        return self.lang


# Глобальный экземпляр для использования в приложении
_i18n = I18n()


def t(key, **kwargs):
    """Глобальная функция перевода"""
    return _i18n.t(key, **kwargs)


def get_lang():
    """Возвращает текущий язык"""
    return _i18n.get_lang()
