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

# ── Проверка существующей установки ───────
EXISTING_INSTALL=false
LSWITCH_RUNNING=false

if command -v lswitch &>/dev/null; then
    EXISTING_INSTALL=true
    echo -e "${YELLOW}⚠️  Обнаружена существующая установка LSwitch${NC}"
    
    # Проверяем, запущен ли демон
    if systemctl --user is-active lswitch &>/dev/null; then
        LSWITCH_RUNNING=true
        echo -e "   Демон LSwitch запущен"
    fi
    
    echo
    echo -e "${CYAN}Это переустановка/обновление существующей версии.${NC}"
    echo -e "Текущая версия: $(lswitch --version 2>/dev/null || echo 'неизвестна')"
    echo
    
    read -p "Продолжить переустановку? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Установка отменена${NC}"
        exit 0
    fi
    
    # Останавливаем демон перед обновлением
    if [ "$LSWITCH_RUNNING" = true ]; then
        echo -e "${YELLOW}⏸  Останавливаю демон для обновления...${NC}"
        systemctl --user stop lswitch 2>/dev/null || true
    fi
    
    # Убиваем все процессы lswitch (включая запущенные вручную через lswitch --debug)
    if pgrep -f "lswitch" >/dev/null 2>&1; then
        echo -e "${YELLOW}⏸  Останавливаю процессы lswitch...${NC}"
        pkill -f "python.*lswitch" 2>/dev/null || true
        pkill -f "lswitch --" 2>/dev/null || true
        # Даём процессам время завершиться
        sleep 1
    fi
    echo
fi

# ── Проверки ──────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ python3 не найден. Установите Python 3.8+${NC}"
    exit 1
fi

# Проверка версии Python (требуется 3.8+)
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; }; then
    echo -e "${RED}❌ Python 3.8+ требуется (найдено $PY_VERSION)${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python $PY_VERSION"

if ! command -v pip3 &>/dev/null; then
    echo -e "${RED}❌ pip3 не найден. Установите: sudo apt install python3-pip${NC}"
    exit 1
fi

# Предупреждение о Wayland
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    echo -e "${YELLOW}⚠  Внимание: обнаружен Wayland${NC}"
    echo -e "   LSwitch оптимизирован для X11. Некоторые функции могут работать ограниченно.${NC}"
    echo
fi

# ── Системные зависимости ─────────────────
echo -e "${YELLOW}📦 Установка системных зависимостей...${NC}"

DEPS_FAILED=0
if command -v apt-get &>/dev/null; then
    # Обновляем apt cache (игнорируем предупреждения от сторонних репозиториев)
    echo -e "   Обновление списка пакетов..."
    sudo apt-get update -qq 2>&1 | grep -E "^(E:|Err:)" || true
    
    echo -e "   Установка python3-dev, xclip, xdotool..."
    if ! sudo apt-get install -y python3-dev xclip xdotool 2>&1 | grep -v "^W:"; then
        echo -e "   ${RED}✗${NC} Ошибка установки через apt-get"
        DEPS_FAILED=1
    fi
elif command -v dnf &>/dev/null; then
    if ! sudo dnf install -y python3-devel xclip xdotool; then
        echo -e "   ${RED}✗${NC} Ошибка установки через dnf"
        DEPS_FAILED=1
    fi
elif command -v pacman &>/dev/null; then
    if ! sudo pacman -S --noconfirm python xclip xdotool; then
        echo -e "   ${RED}✗${NC} Ошибка установки через pacman"
        DEPS_FAILED=1
    fi
else
    echo -e "   ${YELLOW}⚠${NC} Неизвестный менеджер пакетов. Установите вручную:"
    echo -e "      python3-dev, xclip, xdotool"
    DEPS_FAILED=1
fi

if [ $DEPS_FAILED -eq 1 ]; then
    echo -e "${RED}❌ Не удалось установить системные зависимости${NC}"
    exit 1
fi
echo -e "   ${GREEN}✓${NC} Системные зависимости установлены"

# ── Установка пакета ──────────────────────
echo -e "${YELLOW}📦 Установка LSwitch через pip...${NC}"
cd "$SCRIPT_DIR"

# Python 3.12+ требует --break-system-packages (PEP 668)
PIP_EXTRA=""
if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 12 ]; then
    PIP_EXTRA="--break-system-packages"
fi

# Устанавливаем с GUI зависимостями (PyQt5)
echo -e "   Установка базовых зависимостей..."
if ! sudo pip3 install $PIP_EXTRA -e .; then
    echo -e "${RED}❌ Не удалось установить пакет${NC}"
    exit 1
fi

echo -e "   Установка GUI зависимостей (PyQt5)..."
if ! sudo pip3 install $PIP_EXTRA -e ".[gui]"; then
    echo -e "${YELLOW}⚠  GUI зависимости не установлены. lswitch-control может не работать.${NC}"
fi

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

# Автозапуск панели — в пользовательскую директорию (можно отключить через GUI)
mkdir -p "$HOME/.config/autostart"
cp -v "$SCRIPT_DIR/config/lswitch-control.desktop" "$HOME/.config/autostart/lswitch-control.desktop"

# Удаляем старый системный autostart если есть (от предыдущих версий)
if [ -f "/etc/xdg/autostart/lswitch-control.desktop" ]; then
    echo -e "   ${YELLOW}⚠${NC} Удаляю системный /etc/xdg/autostart/lswitch-control.desktop"
    sudo rm -f /etc/xdg/autostart/lswitch-control.desktop
fi

# Удаляем старый user-level override если есть (приоритет выше /etc)
if [ -f "$HOME/.config/systemd/user/lswitch.service" ]; then
    echo -e "   ${YELLOW}⚠${NC} Удаляю старый ~/.config/systemd/user/lswitch.service"
    rm -f "$HOME/.config/systemd/user/lswitch.service"
fi
echo -e "   ${GREEN}✓${NC} Системные файлы установлены"

# ── Проверка установки ───────────────────
echo -e "${YELLOW}🔍 Проверка установки...${NC}"

# Проверка entry points
for cmd in lswitch lswitch-control; do
    if command -v "$cmd" &>/dev/null; then
        echo -e "   ${GREEN}✓${NC} $cmd → $(which $cmd)"
    else
        echo -e "   ${RED}✗${NC} $cmd не найден в PATH"
    fi
done

# Проверка системных утилит
for tool in xclip xdotool; do
    if command -v "$tool" &>/dev/null; then
        echo -e "   ${GREEN}✓${NC} $tool"
    else
        echo -e "   ${RED}✗${NC} $tool не найден (критично)${NC}"
        exit 1
    fi
done

# Проверка Python зависимостей
if python3 -c "import PyQt5" 2>/dev/null; then
    echo -e "   ${GREEN}✓${NC} PyQt5 (GUI)"
else
    echo -e "   ${YELLOW}⚠${NC} PyQt5 не найден (GUI не будет работать)"
fi

if python3 -c "import evdev" 2>/dev/null; then
    echo -e "   ${GREEN}✓${NC} evdev"
else
    echo -e "   ${RED}✗${NC} evdev не найден (критично)${NC}"
    exit 1
fi

if python3 -c "import Xlib" 2>/dev/null; then
    echo -e "   ${GREEN}✓${NC} python-xlib"
else
    echo -e "   ${YELLOW}⚠${NC} python-xlib не найден (рекомендуется)${NC}"
fi

# ── Права доступа к input ─────────────────
echo -e "${YELLOW}🔐 Настройка прав доступа...${NC}"

# Группа input
NEED_RELOGIN=false
if ! groups "$USER" | grep -q '\binput\b'; then
    echo -e "   Добавляю пользователя $USER в группу input..."
    
    if sudo usermod -a -G input "$USER"; then
        # Проверяем, что действительно добавилось
        if getent group input | grep -q "\b$USER\b"; then
            echo -e "   ${GREEN}✓${NC} Пользователь $USER добавлен в группу input"
            NEED_RELOGIN=true
        else
            echo -e "   ${RED}✗${NC} Не удалось проверить добавление в группу"
            NEED_RELOGIN=true
        fi
    else
        echo -e "${RED}❌ Не удалось добавить пользователя в группу input!${NC}"
        echo -e "${YELLOW}Попробуйте вручную:${NC}"
        echo -e "  sudo usermod -a -G input $USER"
        echo -e "  Затем перелогиньтесь"
        echo
        echo -e "${RED}LSwitch не будет работать без доступа к /dev/input!${NC}"
        exit 1
    fi
else
    echo -e "   ${GREEN}✓${NC} Пользователь уже в группе input"
fi

# udev правила
# Убеждаемся, что модуль uinput загружен
if ! lsmod | grep -q "^uinput"; then
    echo -e "   Загрузка модуля uinput..."
    sudo modprobe uinput 2>/dev/null || true
fi

sudo udevadm control --reload-rules 2>/dev/null || true
sudo udevadm trigger 2>/dev/null || true
# Применяем правило именно к uinput
sudo udevadm trigger --name-match=uinput 2>/dev/null || true
echo -e "   ${GREEN}✓${NC} udev правила обновлены"

# Проверяем, что /dev/uinput теперь доступен группе input
if [ -e /dev/uinput ]; then
    UINPUT_GROUP=$(stat -c '%G' /dev/uinput)
    UINPUT_PERMS=$(stat -c '%a' /dev/uinput)
    if [ "$UINPUT_GROUP" = "input" ] && [[ "$UINPUT_PERMS" == *6* ]]; then
        echo -e "   ${GREEN}✓${NC} /dev/uinput доступен группе input ($UINPUT_PERMS $UINPUT_GROUP)"
    else
        echo -e "   ${YELLOW}⚠${NC} /dev/uinput: права $UINPUT_PERMS, группа $UINPUT_GROUP"
        echo -e "      Попробуйте перезагрузить систему для применения udev правил"
    fi
else
    echo -e "   ${YELLOW}⚠${NC} /dev/uinput не найден (модуль uinput может не загрузиться до перезагрузки)"
fi

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
if [ "$NEED_RELOGIN" = true ]; then
    echo -e "${YELLOW}⚠️  ВАЖНО: ПЕРЕЛОГИНЬТЕСЬ!${NC}"
    echo -e "${YELLOW}Вы были добавлены в группу input.${NC}"
    echo -e "${YELLOW}Для применения изменений необходимо:${NC}"
    echo -e "  1. Выйти из системы (logout)"
    echo -e "  2. Войти заново"
    echo -e "  3. Проверить: ${CYAN}groups | grep input${NC}"
    echo
fi
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

# Управление сервисом после установки
if [ "$LSWITCH_RUNNING" = true ]; then
    # Это переустановка - перезапускаем сервис
    echo -e "${YELLOW}🔄 Перезапускаю демон...${NC}"
    if systemctl --user restart lswitch 2>/dev/null; then
        sleep 1
        if systemctl --user is-active lswitch &>/dev/null; then
            echo -e "${GREEN}✅ Демон перезапущен!${NC}"
        else
            echo -e "${YELLOW}⚠  Демон запущен, но статус неизвестен${NC}"
        fi
    else
        echo -e "${RED}❌ Не удалось перезапустить демон${NC}"
        echo -e "   Попробуйте вручную: ${CYAN}systemctl --user restart lswitch${NC}"
    fi
elif [ "$EXISTING_INSTALL" = true ]; then
    # Было установлено, но не запущено - предлагаем запустить
    if systemctl --user is-enabled lswitch &>/dev/null; then
        echo -e "${YELLOW}🔄 Запускаю демон...${NC}"
        systemctl --user start lswitch
        echo -e "${GREEN}✅ Демон запущен!${NC}"
    else
        read -p "Включить автозапуск и запустить? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            systemctl --user enable --now lswitch
            echo -e "${GREEN}✅ Автозапуск включён, демон запущен!${NC}"
        fi
    fi
else
    # Новая установка - спрашиваем про автозапуск
    read -p "Включить автозапуск? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl --user enable --now lswitch
        echo -e "${GREEN}✅ Автозапуск включён, демон запущен!${NC}"
    fi
fi
