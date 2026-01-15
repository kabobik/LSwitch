#!/bin/bash
# Скрипт для безопасного обновления lswitch

set -e

echo "🔄 Обновляю пакет и перезапускаю сервис..."
if command -v python3 >/dev/null 2>&1; then
    echo "   Попытка: python3 -m pip install --upgrade /home/anton/VsCode/LSwitch"
    sudo python3 -m pip install --upgrade /home/anton/VsCode/LSwitch || echo "   ⚠️ pip upgrade failed — fallback to copying files"
fi

echo "🔄 Перезапускаю systemd unit..."
sudo systemctl daemon-reload || true
sudo systemctl restart lswitch.service || sudo systemctl start lswitch.service

sleep 2

echo "✅ Статус:"
sudo systemctl status lswitch.service --no-pager -l || true

echo ""
journalctl -u lswitch.service -n 5 --no-pager
