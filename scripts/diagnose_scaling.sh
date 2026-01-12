#!/bin/bash
# Скрипт для диагностики масштабирования в LSwitch

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         Диагностика масштабирования LSwitch                    ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "=== 1. Информация о мониторе ==="
echo -n "Логический DPI: "
xdpyinfo 2>/dev/null | grep 'resolution:' | head -1 | awk '{print $2}'

echo -n "Размер экрана (пиксели): "
xdpyinfo 2>/dev/null | grep 'dimensions:' | awk '{print $2, $3, $4}'

echo -n "Размер экрана (миллиметры): "
xdpyinfo 2>/dev/null | grep 'dimensions:' | awk '{print $5, $6, $7}'

echo ""
echo "=== 2. Переменные окружения ==="
echo "QT_SCALE_FACTOR=$QT_SCALE_FACTOR"
echo "QT_AUTO_SCREEN_SCALE_FACTOR=$QT_AUTO_SCREEN_SCALE_FACTOR"
echo "GDK_SCALE=$GDK_SCALE"
echo "GDK_DPI_SCALE=$GDK_DPI_SCALE"
echo "QT_SCREEN_SCALE_FACTORS=$QT_SCREEN_SCALE_FACTORS"

echo ""
echo "=== 3. GNOME параметры ==="
if command -v gsettings &> /dev/null; then
    echo -n "text-scaling-factor: "
    gsettings get org.gnome.desktop.interface text-scaling-factor 2>/dev/null || echo "Не найдено"
    
    echo -n "scale-to-fit: "
    gsettings get org.gnome.desktop.interface scaling-factor 2>/dev/null || echo "Не найдено"
else
    echo "gsettings не найден (не GNOME)"
fi

echo ""
echo "=== 4. Окружение рабочего стола ==="
echo "Desktop: $XDG_CURRENT_DESKTOP"
echo "Display Server: $DISPLAY"
echo "Wayland: $WAYLAND_DISPLAY"

echo ""
echo "=== 5. Информация о дисплее (xrandr) ==="
if command -v xrandr &> /dev/null; then
    xrandr 2>/dev/null | grep -E '(^[^ ]|connected|primary)' | head -10
else
    echo "xrandr не найден"
fi

echo ""
echo "=== 6. Логирование LSwitch масштабирования ==="
echo "Запуск LSwitch Control Panel на 3 секунды..."
echo ""

timeout 3 /usr/local/bin/lswitch-control 2>&1 | grep -E '(масштаб|DPI|Финальный|Рассчитан)' || echo "Не удалось запустить lswitch-control"

echo ""
echo "=== 7. Рекомендации ==="

# Проверяем DPI
LOGICAL_DPI=$(xdpyinfo 2>/dev/null | grep 'resolution:' | head -1 | awk '{print $2}' | cut -d'x' -f1)

if [ -z "$LOGICAL_DPI" ]; then
    echo "⚠️  Не удалось определить DPI"
else
    if [ "$LOGICAL_DPI" -le 96 ]; then
        echo "✓ DPI в норме для стандартного монитора (96 DPI)"
    elif [ "$LOGICAL_DPI" -le 110 ]; then
        echo "⚠️  Немного повышенный DPI ($LOGICAL_DPI), масштабирование ~1.15x"
        echo "   Если интерфейс слишком мал, попробуйте:"
        echo "   export QT_SCALE_FACTOR=$((LOGICAL_DPI / 96)).$(((LOGICAL_DPI % 96) * 10 / 96))"
    else
        echo "⚠️  Высокий DPI ($LOGICAL_DPI), это HiDPI монитор"
        echo "   Приложение должно автоматически масштабироваться"
        echo "   Если интерфейс неправильного размера, проверьте физический DPI монитора"
    fi
fi

echo ""
echo "Для подробной информации смотрите: docs/SCALING.md"
