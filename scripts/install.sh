#!/bin/bash
# Скрипт установки LSwitch в систему

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   LSwitch - Установка в систему        ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo

# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Запустите скрипт с правами root:${NC}"
    echo -e "   sudo ./install.sh"
    exit 1
fi

echo -e "${YELLOW}📦 Установка зависимостей...${NC}"
apt-get update -qq
apt-get install -y python3-evdev python3-pyqt5 xclip xdotool

echo -e "${YELLOW}📁 Установка пакета и копирование GUI...${NC}"
# Предпочтительная установка через pip (если доступна) — это установит пакет и консольный скрипт
if command -v python3 >/dev/null 2>&1; then
    echo "   Попытка: python3 -m pip install --upgrade ."
    if python3 -m pip install --upgrade .; then
        echo "   ✓ Пакет установлен через pip"
    else
        echo "   ⚠️  pip install завершился с ошибкой — выполню fallback copy"
        install -m 755 lswitch.py /usr/local/bin/lswitch || true
    fi
else
    echo "   ⚠️ python3 не найден — выполняю fallback copy"
    install -m 755 lswitch.py /usr/local/bin/lswitch || true
fi

# GUI: панель управления всё ещё копируем в системные пути (desktop file и исполняемый скрипт)
install -m 755 lswitch_control.py /usr/local/bin/lswitch-control || true
install -m 755 lswitch_tray.py /usr/local/bin/lswitch-tray || true

# Копируем иконку
install -Dm644 lswitch.svg /usr/share/pixmaps/lswitch.svg

# Устанавливаем .desktop файлы
install -Dm644 lswitch-tray.desktop /usr/share/applications/lswitch-tray.desktop
install -Dm644 lswitch-control.desktop /usr/share/applications/lswitch-control.desktop
# Автозапуск: используем новую панель управления
install -Dm644 lswitch-control.desktop /etc/xdg/autostart/lswitch-control.desktop

# Создаём директорию конфигурации
mkdir -p /etc/lswitch
install -m 664 config.json /etc/lswitch/config.json
# Делаем доступным для группы input (для GUI без sudo)
chgrp input /etc/lswitch/config.json 2>/dev/null || true

echo -e "${YELLOW}🔐 Настройка прав доступа (input devices)...${NC}"
# Устанавливаем udev правило для доступа к input устройствам
install -Dm644 99-lswitch.rules /etc/udev/rules.d/99-lswitch.rules

# Перезагружаем udev правила
udevadm control --reload-rules
udevadm trigger

# Создаём группу input если её нет
if ! getent group input > /dev/null 2>&1; then
    groupadd -r input
    echo -e "   ✓ Группа input создана"
fi

echo -e "${YELLOW}⚙️  Установка systemd сервиса...${NC}"

# Определяем пользователя X-сессии
X_USER=$(who | grep -E "\(:0\)" | awk '{print $1}' | head -n1)
if [ -z "$X_USER" ]; then
    X_USER=$(logname 2>/dev/null || echo "$SUDO_USER")
fi

if [ -z "$X_USER" ]; then
    echo -e "${RED}⚠️  Не удалось определить пользователя X-сессии${NC}"
    echo -e "   Укажите вручную в /etc/systemd/system/lswitch.service"
    X_USER="anton"
fi

echo -e "   Пользователь X-сессии: ${GREEN}$X_USER${NC}"

# Добавляем пользователя в группу input (для работы без root)
usermod -a -G input $X_USER
echo -e "   ✓ Пользователь $X_USER добавлен в группу 'input'"
echo -e "   ${YELLOW}⚠️  ВАЖНО: Перелогиньтесь для применения прав!${NC}"
echo

X_AUTH="/home/$X_USER/.Xauthority"

# Копируем unit файл и подставляем переменные
sed -e "s|XAUTHORITY=/home/anton/.Xauthority|XAUTHORITY=$X_AUTH|" \
    lswitch.service > /etc/systemd/system/lswitch.service

# Перезагружаем systemd
systemctl daemon-reload

echo
echo -e "${GREEN}✅ Установка завершена!${NC}"
echo
echo -e "${YELLOW}Управление сервисом:${NC}"
echo -e "  • Запустить:           sudo systemctl start lswitch"
echo -e "  • Остановить:          sudo systemctl stop lswitch"
echo -e "  • Перезапустить:       sudo systemctl restart lswitch"
echo -e "  • Статус:              sudo systemctl status lswitch"
echo -e "  • Включить автозапуск: ${GREEN}sudo systemctl enable lswitch${NC}"
echo -e "  • Отключить автозапуск: sudo systemctl disable lswitch"
echo
echo -e "${YELLOW}Логи:${NC}"
echo -e "  sudo journalctl -u lswitch -f"
echo
echo -e "${YELLOW}Конфигурация:${NC}"
echo -e "  /etc/lswitch/config.json"
echo
read -p "Включить автозапуск при загрузке системы? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl enable lswitch
    systemctl start lswitch
    echo -e "${GREEN}✅ Автозапуск включён и сервис запущен!${NC}"
else
    echo -e "${YELLOW}Сервис установлен, но не запущен.${NC}"
    echo -e "Запустите вручную: ${GREEN}sudo systemctl start lswitch${NC}"
fi
echo
