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
                'settings_title': 'LSwitch Settings',
                'settings_page_general': 'General',
                'settings_page_auto': 'Auto-correction',
                'settings_page_dictionaries': 'Dictionaries',
                'settings_page_selection': 'Selection',
                'settings_page_advanced': 'Advanced',
                'settings_reset_page': 'Reset page',
                'settings_reset_all': 'Reset all',
                'settings_cancel': 'Cancel',
                'settings_apply': 'Apply',
                'settings_ok': 'OK',
                'settings_browse': 'Browse…',
                'settings_seconds': 's',
                'settings_platform': 'Current session',
                'settings_config_path': 'Configuration file',
                'settings_trace_override': '--trace is active; the process log level remains TRACE.',
                'settings_external_change': 'Settings changed outside this window. Your edited fields were preserved and will be merged on Apply.',
                'settings_dependency_disabled': 'Enable the parent feature to edit this setting.',
                'settings_applying': 'Applying settings…',
                'settings_applied': 'Settings applied.',
                'settings_unknown_error': 'Unknown settings error',
                'settings_error_title': 'Could not apply settings',
                'settings_choose_dictionary': 'Choose dictionary',
                'settings_dictionary_filter': 'Dictionary files (*.dic);;All files (*)',
                'settings_strategy_auto': 'Automatic',
                'settings_strategy_clipboard': 'Clipboard copy/paste',
                'settings_strategy_primary': 'PRIMARY selection and direct typing',
                'settings_strategy_disabled': 'Disabled',
                'settings_shortcut_help': 'Direct XKB/D-Bus switching is preferred. This shortcut is used only as a verified fallback.',
                'settings_strategy_help_auto': 'Reads PRIMARY first and falls back to clipboard copy/paste.',
                'settings_strategy_help_clipboard_copy': 'Always copies and replaces through the clipboard, then restores it.',
                'settings_strategy_help_primary_selection': 'Reads PRIMARY and types replacement text directly in the target layout.',
                'settings_strategy_help_disabled': 'Disables selection conversion on Wayland.',
                'settings_double_click_timeout': 'Double Shift interval',
                'settings_switch_layout_after_convert': 'Keep result layout after conversion',
                'settings_layout_switch_key': 'Fallback layout shortcut',
                'settings_auto_switch': 'Automatic conversion at word boundary',
                'settings_auto_switch_threshold': 'Minimum characters before auto-conversion',
                'settings_auto_switch_mid_word': 'Automatic conversion while typing a word',
                'settings_mid_word_min_prefix_len': 'Minimum prefix length',
                'settings_system_dict_enabled': 'Use system dictionaries',
                'settings_system_dict_en_path': 'English dictionary (.dic)',
                'settings_system_dict_ru_path': 'Russian dictionary (.dic)',
                'settings_user_dict_enabled': 'Enable self-learning dictionary',
                'settings_user_dict_auto_confirm': 'Confirm accepted auto-conversions automatically',
                'settings_user_dict_min_weight': 'Minimum learned-word weight',
                'settings_wayland_selection_strategy': 'Wayland selection strategy',
                'settings_x11_selection_timing_poll_interval': 'X11 selection polling interval',
                'settings_x11_selection_timing_paste_delay': 'X11 delay before paste',
                'settings_x11_selection_timing_restore_delay': 'X11 delay before clipboard restore',
                'settings_x11_selection_timing_expand_selection_delay': 'X11 selection expansion delay',
                'settings_wayland_timing_wl_clipboard_timeout': 'wl-clipboard command timeout',
                'settings_wayland_selection_timing_copy_wait_timeout': 'Wayland copy wait timeout',
                'settings_wayland_selection_timing_copy_poll_interval': 'Wayland copy polling interval',
                'settings_wayland_selection_timing_copy_retry_delay': 'Wayland copy retry delay',
                'settings_wayland_selection_timing_paste_delay': 'Wayland delay before paste',
                'settings_wayland_selection_timing_restore_delay': 'Wayland delay before clipboard restore',
                'settings_wayland_selection_timing_expand_selection_delay': 'Wayland selection expansion delay',
                'settings_debug': 'Debug logging and monitor',
                'settings_timing_key_press_delay': 'Virtual key press delay',
                'settings_timing_key_repeat_delay': 'Virtual key repeat delay',
                'settings_timing_retype_before_replay_delay': 'Retype delay before replay',
                'settings_timing_direct_type_after_layout_switch_delay': 'Direct typing delay after layout switch',
                'settings_timing_undo_before_replay_delay': 'Undo delay before replay',
                'settings_timing_auto_before_replay_delay': 'Auto-conversion delay before replay',
                'settings_timing_auto_before_space_delay': 'Auto-conversion delay before Space',
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
                'settings_title': 'Настройки LSwitch',
                'settings_page_general': 'Основные',
                'settings_page_auto': 'Автокоррекция',
                'settings_page_dictionaries': 'Словари',
                'settings_page_selection': 'Выделение',
                'settings_page_advanced': 'Дополнительно',
                'settings_reset_page': 'Сбросить страницу',
                'settings_reset_all': 'Сбросить всё',
                'settings_cancel': 'Отмена',
                'settings_apply': 'Применить',
                'settings_ok': 'OK',
                'settings_browse': 'Обзор…',
                'settings_seconds': 'с',
                'settings_platform': 'Текущая сессия',
                'settings_config_path': 'Файл конфигурации',
                'settings_trace_override': 'Активен --trace: уровень журналирования процесса останется TRACE.',
                'settings_external_change': 'Настройки изменились вне этого окна. Ваши правки сохранены и будут объединены при применении.',
                'settings_dependency_disabled': 'Включите родительскую функцию, чтобы изменить этот параметр.',
                'settings_applying': 'Применение настроек…',
                'settings_applied': 'Настройки применены.',
                'settings_unknown_error': 'Неизвестная ошибка настроек',
                'settings_error_title': 'Не удалось применить настройки',
                'settings_choose_dictionary': 'Выбор словаря',
                'settings_dictionary_filter': 'Файлы словарей (*.dic);;Все файлы (*)',
                'settings_strategy_auto': 'Автоматически',
                'settings_strategy_clipboard': 'Копирование и вставка через буфер',
                'settings_strategy_primary': 'PRIMARY и прямой ввод',
                'settings_strategy_disabled': 'Отключено',
                'settings_shortcut_help': 'В приоритете прямое переключение через XKB/D-Bus. Комбинация используется только как проверяемый резервный способ.',
                'settings_strategy_help_auto': 'Сначала читает PRIMARY, затем при необходимости использует копирование и вставку.',
                'settings_strategy_help_clipboard_copy': 'Всегда заменяет через буфер обмена и затем восстанавливает его.',
                'settings_strategy_help_primary_selection': 'Читает PRIMARY и напрямую вводит замену в целевой раскладке.',
                'settings_strategy_help_disabled': 'Отключает конвертацию выделения в Wayland.',
                'settings_double_click_timeout': 'Интервал двойного Shift',
                'settings_switch_layout_after_convert': 'Оставлять раскладку результата после конвертации',
                'settings_layout_switch_key': 'Резервная комбинация переключения',
                'settings_auto_switch': 'Автоконвертация на границе слова',
                'settings_auto_switch_threshold': 'Минимум символов до автоконвертации',
                'settings_auto_switch_mid_word': 'Автоконвертация во время набора слова',
                'settings_mid_word_min_prefix_len': 'Минимальная длина префикса',
                'settings_system_dict_enabled': 'Использовать системные словари',
                'settings_system_dict_en_path': 'Английский словарь (.dic)',
                'settings_system_dict_ru_path': 'Русский словарь (.dic)',
                'settings_user_dict_enabled': 'Включить самообучающийся словарь',
                'settings_user_dict_auto_confirm': 'Автоматически подтверждать принятые автоконвертации',
                'settings_user_dict_min_weight': 'Минимальный вес изученного слова',
                'settings_wayland_selection_strategy': 'Стратегия выделения Wayland',
                'settings_x11_selection_timing_poll_interval': 'Интервал опроса выделения X11',
                'settings_x11_selection_timing_paste_delay': 'Задержка X11 перед вставкой',
                'settings_x11_selection_timing_restore_delay': 'Задержка X11 перед восстановлением буфера',
                'settings_x11_selection_timing_expand_selection_delay': 'Задержка расширения выделения X11',
                'settings_wayland_timing_wl_clipboard_timeout': 'Таймаут команды wl-clipboard',
                'settings_wayland_selection_timing_copy_wait_timeout': 'Таймаут ожидания копирования Wayland',
                'settings_wayland_selection_timing_copy_poll_interval': 'Интервал проверки копирования Wayland',
                'settings_wayland_selection_timing_copy_retry_delay': 'Задержка повтора копирования Wayland',
                'settings_wayland_selection_timing_paste_delay': 'Задержка Wayland перед вставкой',
                'settings_wayland_selection_timing_restore_delay': 'Задержка Wayland перед восстановлением буфера',
                'settings_wayland_selection_timing_expand_selection_delay': 'Задержка расширения выделения Wayland',
                'settings_debug': 'Отладочное журналирование и монитор',
                'settings_timing_key_press_delay': 'Задержка нажатия виртуальной клавиши',
                'settings_timing_key_repeat_delay': 'Задержка повтора виртуальной клавиши',
                'settings_timing_retype_before_replay_delay': 'Задержка перед повтором набора',
                'settings_timing_direct_type_after_layout_switch_delay': 'Задержка прямого ввода после смены раскладки',
                'settings_timing_undo_before_replay_delay': 'Задержка отмены перед повтором',
                'settings_timing_auto_before_replay_delay': 'Задержка автоконвертации перед повтором',
                'settings_timing_auto_before_space_delay': 'Задержка автоконвертации перед пробелом',
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
