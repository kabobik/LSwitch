#!/bin/bash
# Скрипт диагностики LSwitch

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║   LSwitch - Диагностика                ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════╝${NC}"
echo

echo -e "${YELLOW}1. Проверка установленных файлов:${NC}"
echo -n "   /usr/local/bin/lswitch: "
if [ -f /usr/local/bin/lswitch ]; then
    echo -e "${GREEN}✓${NC}"
    ls -lh /usr/local/bin/lswitch
else
    echo -e "${RED}✗ Не найден${NC}"
fi

echo -n "   /etc/lswitch/config.json: "
if [ -f /etc/lswitch/config.json ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗ Не найден${NC}"
fi

echo -n "   /etc/systemd/system/lswitch.service: "
if [ -f /etc/systemd/system/lswitch.service ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗ Не найден${NC}"
fi

echo
echo -e "${YELLOW}2. Проверка зависимостей:${NC}"
echo -n "   python3: "
if command -v python3 &> /dev/null; then
    echo -e "${GREEN}✓ $(python3 --version)${NC}"
else
    echo -e "${RED}✗ Не установлен${NC}"
fi

echo -n "   python3-evdev: "
if python3 -c "import evdev" 2>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗ Не установлен${NC}"
    echo -e "      Установите: ${YELLOW}sudo apt install python3-evdev${NC}"
fi

echo
echo -e "${YELLOW}3. Проверка прав доступа:${NC}"
echo -n "   /dev/input/: "
if [ -r /dev/input/event0 ] 2>/dev/null || [ "$(id -u)" -eq 0 ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗ Нужны права root${NC}"
fi

echo
echo -e "${YELLOW}4. Статус systemd сервиса:${NC}"
if systemctl list-unit-files | grep -q lswitch.service; then
    systemctl status lswitch.service --no-pager -l || true
    echo
    echo -e "${YELLOW}   Переменные окружения сервиса:${NC}"
    sudo systemctl show lswitch | grep "Environment=" | sed 's/^/   /'
else
    echo -e "${RED}   Сервис не установлен${NC}"
fi

echo
echo -e "${YELLOW}5. Последние логи (если сервис запущен):${NC}"
if systemctl is-active --quiet lswitch; then
    journalctl -u lswitch -n 20 --no-pager
else
    echo -e "${RED}   Сервис не запущен${NC}"
fi

echo
echo -e "${YELLOW}6. Тест запуска вручную:${NC}"
if [ "$EUID" -eq 0 ]; then
    echo "   Попытка запуска (Ctrl+C для остановки через 5 сек)..."
    timeout 5 /usr/bin/python3 /usr/local/bin/lswitch 2>&1 || true
else
    echo -e "${YELLOW}   Запустите с правами root для теста:${NC}"
    echo -e "   ${GREEN}sudo $0${NC}"
fi

echo
echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║   Рекомендации:                        ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════╝${NC}"
echo
echo "• Если сервис не запущен:"
echo "  sudo systemctl start lswitch"
echo
echo "• Если есть ошибки в логах:"
echo "  sudo journalctl -u lswitch -n 50"
echo
echo "• Для ручного тестирования:"
echo "  sudo /usr/bin/python3 /usr/local/bin/lswitch"
echo
