#!/bin/bash
# Проверка и настройка автозапуска LSwitch

echo "=== LSwitch - Проверка автозапуска ==="
echo

# Проверка GUI автозапуска
echo "1. GUI режим (автозапуск при входе в систему):"
if [ -f "$HOME/.config/autostart/lswitch-tray.desktop" ] || [ -f "/etc/xdg/autostart/lswitch-tray.desktop" ]; then
    echo "   ✅ Автозапуск настроен"
    if [ -f "$HOME/.config/autostart/lswitch-tray.desktop" ]; then
        echo "      Файл: ~/.config/autostart/lswitch-tray.desktop"
    fi
    if [ -f "/etc/xdg/autostart/lswitch-tray.desktop" ]; then
        echo "      Файл: /etc/xdg/autostart/lswitch-tray.desktop"
    fi
else
    echo "   ❌ Автозапуск НЕ настроен"
    echo "      Настроить: cp lswitch-tray.desktop ~/.config/autostart/"
fi
echo

# Проверка systemd демона
echo "2. Systemd демон (запуск при загрузке системы):"
if systemctl is-enabled lswitch.service &>/dev/null; then
    echo "   ✅ Автозапуск включен"
    systemctl status lswitch.service | head -3
else
    echo "   ❌ Автозапуск выключен"
    echo "      Включить: sudo systemctl enable lswitch"
fi
echo

# Рекомендации
echo "📋 Рекомендации:"
echo
echo "Используйте ТОЛЬКО ОДИН режим одновременно!"
echo
echo "Для desktop окружений (GNOME, KDE, XFCE):"
echo "  ✅ GUI режим - работает автоматически после установки"
echo "  ✅ Запускается при входе пользователя в систему"
echo "  ✅ Управление через иконку в трее"
echo
echo "Для серверов или минимальных установок:"
echo "  ✅ Systemd демон - sudo systemctl enable lswitch"
echo "  ✅ Запускается при загрузке системы (от root)"
echo "  ✅ Работает без GUI"
echo

# Проверка прав
echo "3. Проверка прав доступа:"
if groups | grep -q input; then
    echo "   ✅ Пользователь в группе 'input'"
else
    echo "   ❌ НЕТ в группе 'input' - требуется перелогин после установки!"
    echo "      После установки обязательно перелогиньтесь (выйдите и войдите)"
fi
echo

# Текущее состояние
echo "4. Текущее состояние:"
if pgrep -f "lswitch" > /dev/null; then
    echo "   ✅ LSwitch запущен"
    pgrep -af "lswitch"
else
    echo "   ⚠️  LSwitch НЕ запущен"
fi
echo
