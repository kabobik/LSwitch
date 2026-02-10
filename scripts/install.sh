#!/bin/bash
# ═══════════════════════════════════════════
# LSwitch — Установка в систему
# Единственный способ: pip3 install + post-install
# ═══════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   LSwitch — Установка v1.1             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo

# ── Проверки ──────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ python3 не найден. Установите Python 3.8+${NC}"
    exit 1
fi

if ! command -v pip3 &>/dev/null; then
    echo -e "${RED}❌ pip3 не найден. Установите: sudo apt install python3-pip${NC}"
    exit 1
fi

# ── Системные зависимости ─────────────────
echo -e "${YELLOW}📦 Установка системных зависимостей...${NC}"
if command -v apt-get &>/dev/null; then
    sudo apt-get install -y -qq python3-dev xclip xdotool 2>/dev/null || true
elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3-devel xclip xdotool 2>/dev/null || true
elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm python xclip xdotool 2>/dev/null || true
fi
echo -e "   ${GREEN}✓${NC} Системные зависимости"

# ── Установка пакета ──────────────────────
echo -e "${YELLOW}📦 Установка LSwitch через pip...${NC}"
cd "$SCRIPT_DIR"

# Python 3.12+ требует --break-system-packages (PEP 668)
PIP_EXTRA=""
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.minor}")')
if [ "$PY_VER" -ge 12 ]; then
    PIP_EXTRA="--break-system-packages"
fi

sudo pip3 install $PIP_EXTRA -e .
echo -e "   ${GREEN}✓${NC} Пакет установлен"

# ── Системные файлы ───────────────────────
# data_files из setup.py не копируются при editable install,
# поэтому устанавливаем их явно
echo -e "${YELLOW}📁 Установка системных файлов...${NC}"
sudo cp -v "$SCRIPT_DIR/assets/lswitch.png" /usr/share/pixmaps/lswitch.png
sudo mkdir -p /etc/systemd/user
sudo cp -v "$SCRIPT_DIR/config/lswitch.service" /etc/systemd/user/lswitch.service
sudo cp -v "$SCRIPT_DIR/config/99-lswitch.rules" /etc/udev/rules.d/99-lswitch.rules
sudo cp -v "$SCRIPT_DIR/config/lswitch-control.desktop" /usr/share/applications/lswitch-control.desktop
sudo mkdir -p /etc/xdg/autostart
sudo cp -v "$SCRIPT_DIR/config/lswitch-control.desktop" /etc/xdg/autostart/lswitch-control.desktop

# Удаляем старый user-level override если есть (приоритет выше /etc)
if [ -f "$HOME/.config/systemd/user/lswitch.service" ]; then
    echo -e "   ${YELLOW}⚠${NC} Удаляю старый ~/.config/systemd/user/lswitch.service"
    rm -f "$HOME/.config/systemd/user/lswitch.service"
fi
echo -e "   ${GREEN}✓${NC} Системные файлы установлены"

# ── Проверка entry points ─────────────────
echo -e "${YELLOW}🔍 Проверка команд...${NC}"
for cmd in lswitch lswitch-control; do
    if command -v "$cmd" &>/dev/null; then
        echo -e "   ${GREEN}✓${NC} $cmd → $(which $cmd)"
    else
        echo -e "   ${RED}✗${NC} $cmd не найден в PATH"
    fi
done

# ── Права доступа к input ─────────────────
echo -e "${YELLOW}🔐 Настройка прав доступа...${NC}"

# Группа input
if ! groups "$USER" | grep -q '\binput\b'; then
    sudo usermod -a -G input "$USER"
    echo -e "   ${GREEN}✓${NC} Пользователь $USER добавлен в группу input"
    echo -e "   ${YELLOW}⚠  Перелогиньтесь для применения!${NC}"
else
    echo -e "   ${GREEN}✓${NC} Пользователь уже в группе input"
fi

# udev правила (устанавливаются через data_files в setup.py)
sudo udevadm control --reload-rules 2>/dev/null || true
sudo udevadm trigger 2>/dev/null || true
echo -e "   ${GREEN}✓${NC} udev правила обновлены"

# ── systemd сервис ───────────────────────
echo -e "${YELLOW}⚙️  Настройка systemd...${NC}"
systemctl --user daemon-reload 2>/dev/null || true
echo -e "   ${GREEN}✓${NC} systemd перезагружен"

# ── Итог ──────────────────────────────────
echo
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✅ Установка завершена!              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo
echo -e "${CYAN}Команды:${NC}"
echo -e "  ${GREEN}systemctl --user enable --now lswitch${NC}  Автозапуск + старт"
echo -e "  ${GREEN}lswitch-control${NC}                        Открыть GUI"
echo -e "  ${GREEN}lswitch --debug${NC}                        Запуск в отладке"
echo
echo -e "${CYAN}Или через make:${NC}"
echo -e "  ${GREEN}make enable${NC}   Автозапуск + старт"
echo -e "  ${GREEN}make status${NC}   Статус демона"
echo -e "  ${GREEN}make logs${NC}     Логи в реальном времени"
echo

read -p "Включить автозапуск? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl --user enable --now lswitch
    echo -e "${GREEN}✅ Автозапуск включён, демон запущен!${NC}"
fi
