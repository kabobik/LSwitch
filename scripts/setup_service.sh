#!/bin/bash
# Быстрая установка systemd службы для lswitch

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Создаём директорию для systemd пользователя
mkdir -p ~/.config/systemd/user

# Создаём service файл
cat > ~/.config/systemd/user/lswitch.service << SERVICEEOF
[Unit]
Description=LSwitch - Layout Switcher Daemon
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $SCRIPT_DIR/lswitch.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
SERVICEEOF

# Перезагружаем systemd
systemctl --user daemon-reload

echo "✅ Служба установлена"
echo "Для запуска: systemctl --user start lswitch"
echo "Для автозапуска: systemctl --user enable lswitch"
