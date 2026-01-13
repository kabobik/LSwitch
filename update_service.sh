#!/bin/bash
# Скрипт для безопасного обновления lswitch

set -e

echo "🔄 Останавливаю сервис..."
sudo systemctl stop lswitch.service

echo "🔄 Убиваю оставшиеся процессы..."
sudo pkill -9 -f "/usr/local/bin/lswitch" 2>/dev/null || true

echo "📦 Копирую файлы..."
sudo cp /home/anton/VsCode/LSwitch/lswitch.py /usr/local/bin/
sudo cp /home/anton/VsCode/LSwitch/user_dictionary.py /usr/local/bin/ 2>/dev/null || true

echo "🚀 Запускаю сервис..."
sudo systemctl start lswitch.service

sleep 2

echo "✅ Статус:"
ps aux | grep "[l]switch"
echo ""
journalctl -u lswitch.service -n 5 --no-pager

echo ""
echo "✅ Готово! Запущен процесс: $(pgrep -f '/usr/local/bin/lswitch')"
