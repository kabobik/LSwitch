#!/bin/bash
# ═══════════════════════════════════════════
# LSwitch — Удаление из системы
# ═══════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║   LSwitch — Удаление из системы        ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════╝${NC}"
echo

# Остановка сервиса
echo -e "${YELLOW}Остановка сервиса...${NC}"
systemctl --user stop lswitch 2>/dev/null || true
systemctl --user disable lswitch 2>/dev/null || true

# Остановка GUI
pkill -f lswitch-control 2>/dev/null || true
pkill -f lswitch_control 2>/dev/null || true

echo -e "${YELLOW}Удаление пакета...${NC}"
sudo pip3 uninstall -y lswitch 2>/dev/null || true

# Очистка системных файлов (data_files из setup.py)
echo -e "${YELLOW}Очистка системных файлов...${NC}"
sudo rm -f /usr/share/applications/lswitch-control.desktop
sudo rm -f /etc/xdg/autostart/lswitch-control.desktop
sudo rm -f /usr/share/pixmaps/lswitch.png
sudo rm -f /etc/udev/rules.d/99-lswitch.rules
sudo rm -f /etc/systemd/user/lswitch.service

# Перезагрузка
systemctl --user daemon-reload 2>/dev/null || true

echo
echo -e "${GREEN}✅ LSwitch успешно удалён!${NC}"
echo
