#!/bin/bash
# Быстрый тест LSwitch без установки

echo "=== LSwitch Quick Test ==="
echo

# Проверка зависимостей
echo "Проверка зависимостей..."
if ! python3 -c "import evdev" 2>/dev/null; then
    echo "❌ python3-evdev не установлен"
    echo "   Установите: sudo apt install python3-evdev"
    exit 1
fi

if ! python3 -c "import PyQt5" 2>/dev/null; then
    echo "⚠️  python3-pyqt5 не установлен (нужен для GUI)"
    echo "   Установите: sudo apt install python3-pyqt5"
    GUI_AVAILABLE=false
else
    GUI_AVAILABLE=true
fi

echo "✓ Зависимости проверены"
echo

# Тест словаря
echo "Тест модуля автопереключения..."
python3 -c "
from dictionary import detect_language, is_likely_wrong_layout
tests = [
    ('привет', 'en', True),
    ('hello', 'ru', True),
    ('ghbdtn', 'en', False),
]
for word, layout, should_convert in tests:
    result = is_likely_wrong_layout(word, layout)
    status = '✓' if result == should_convert else '❌'
    print(f'{status} {word} в {layout}: {result}')
"
echo

# Выбор режима
echo "Выберите режим тестирования:"
echo "1) GUI с треем (требуется X11)"
echo "2) Консольный режим (требуется root)"
read -p "Ваш выбор (1-2): " choice

case $choice in
    1)
        if [ "$GUI_AVAILABLE" = true ]; then
            echo "Запуск GUI..."
            python3 lswitch_tray.py
        else
            echo "❌ PyQt5 не установлен"
        fi
        ;;
    2)
        if [ "$EUID" -ne 0 ]; then
            echo "Требуются права root для доступа к /dev/input/"
            echo "Запуск через sudo..."
            sudo python3 -u lswitch.py
        else
            python3 -u lswitch.py
        fi
        ;;
    *)
        echo "Неверный выбор"
        exit 1
        ;;
esac
