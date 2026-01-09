#!/bin/bash
# Скрипт удаления LSwitch из системы

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║   LSwitch - Удаление из системы        ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════╝${NC}"
echo

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Запустите скрипт с правами root:${NC}"
    echo -e "   sudo ./uninstall.sh"
    exit 1
fi

echo -e "${YELLOW}Остановка сервиса...${NC}"
systemctl stop lswitch 2>/dev/null || true
systemctl disable lswitch 2>/dev/null || true

# Останавливаем GUI процессы
pkill -f lswitch-tray 2>/dev/null || true
pkill -f lswitch_tray.py 2>/dev/null || true

echo -e "${YELLOW}Удаление файлов...${NC}"
rm -f /etc/systemd/system/lswitch.service
rm -f /usr/local/bin/lswitch
rm -f /usr/local/bin/lswitch-tray
rm -f /usr/share/pixmaps/lswitch.svg
rm -f /usr/share/applications/lswitch-tray.desktop
rm -f /etc/xdg/autostart/lswitch-tray.desktop
rm -rf /etc/lswitch

echo -e "${YELLOW}Перезагрузка systemd...${NC}"
systemctl daemon-reload

echo -e "${GREEN}✅ LSwitch успешно удалён из системы!${NC}"
echo
