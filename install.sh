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

# Test-mode: if LSWITCH_TEST_PREFIX is set, install into that prefix and
# avoid making system changes (no apt-get, systemctl, udevadm, usermod, etc.).
TEST_MODE=0
PREFIX=""
LOGFILE=""
if [ -n "$LSWITCH_TEST_PREFIX" ]; then
    TEST_MODE=1
    PREFIX="$LSWITCH_TEST_PREFIX"
    mkdir -p "$PREFIX"
    LOGFILE="$PREFIX/.lswitch_install_log"
    echo "TEST_MODE=1" > "$LOGFILE"
    echo "Test mode active: installing into prefix=$PREFIX" | tee -a "$LOGFILE"
fi

# Helper to run or log commands depending on TEST_MODE
run_or_log() {
    if [ "$TEST_MODE" -eq 1 ]; then
        echo "[TEST_MODE] Would run: $*" | tee -a "$LOGFILE"
    else
        echo "Running: $*"
        eval "$@"
    fi
}

# Helper to copy/install files into prefixed dirs
pref_install() {
    src="$1"; shift
    dest="$1"; shift
    if [ -n "$PREFIX" ]; then
        # map /usr/local -> $PREFIX, /usr/share -> $PREFIX, /etc -> $PREFIX etc
        dest="$PREFIX${dest}"
        mkdir -p "$(dirname "$dest")"
    fi
    if [ "$TEST_MODE" -eq 1 ]; then
        echo "[TEST_MODE] Installing $src -> $dest" | tee -a "$LOGFILE"
        if [ -d "$src" ]; then
            cp -r "$src" "$dest"
        else
            install -m 755 "$src" "$dest" 2>/dev/null || cp "$src" "$dest"
        fi
    else
        install -m 755 "$src" "$dest" 2>/dev/null || cp "$src" "$dest"
    fi
}
# Проверка прав root
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}⚠️  Внимание: скрипт работает без root-прав${NC}"
    echo -e "${YELLOW}   Некоторые операции могут не выполниться${NC}"
    echo -e "${YELLOW}   Для полной установки используйте: sudo ./install.sh${NC}"
    echo
fi

# Определяем пользователя X-сессии для остановки пользовательской службы
# Функция пытается найти пользователя несколькими способами и запрашивает ввод в интерактивном режиме
detect_x_user() {
    # 0) allow explicit override via environment
    if [ -n "$X_USER" ]; then
        echo "$X_USER"
        return 0
    fi
    if [ -n "$LS_USER" ]; then
        echo "$LS_USER"
        return 0
    fi

    # 1) who (:0 session)
    local u
    u=$(who | awk '/\(:0\)/ {print $1; exit}')
    if [ -n "$u" ]; then
        echo "$u"
        return 0
    fi

    # 2) sudo user that invoked the script
    if [ -n "$SUDO_USER" ]; then
        echo "$SUDO_USER"
        return 0
    fi

    # 3) logname (works for interactive shells)
    u=$(logname 2>/dev/null || true)
    if [ -n "$u" ] && [ "$u" != "root" ]; then
        echo "$u"
        return 0
    fi

    # 4) loginctl (find session on :0)
    if command -v loginctl >/dev/null 2>&1; then
        u=$(loginctl list-sessions --no-legend 2>/dev/null | awk '$3==":0" {print $2; exit}')
        if [ -n "$u" ]; then
            echo "$u"
            return 0
        fi
    fi

    # 5) single home directory fallback
    if [ -d /home ]; then
        count=$(ls -1 /home | wc -l)
        if [ "$count" -eq 1 ]; then
            echo "$(ls /home | head -n1)"
            return 0
        fi
    fi

    # 6) prompt the user if we're interactive
    if [ -t 0 ]; then
        read -p "Не удалось определить пользователя X-сессии. Введите имя пользователя (или Enter для отмены): " input_user
        if [ -n "$input_user" ]; then
            echo "$input_user"
            return 0
        else
            echo "Отменено пользователем." >&2
            exit 1
        fi
    fi

    # 7) non-interactive failure
    echo "Не удалось определить пользователя X-сессии и скрипт не интерактивен." >&2
    echo "Установите переменную X_USER вручную и запустите скрипт снова." >&2
    exit 1
}

X_USER=$(detect_x_user)

echo -e "${YELLOW}🛑 Остановка старых версий службы...${NC}"
# Останавливаем системную службу (если запущена)
systemctl stop lswitch.service 2>/dev/null && echo "   ✓ Системная служба остановлена" || true
systemctl disable lswitch.service 2>/dev/null || true

# Останавливаем пользовательскую службу (если запущена)
if [ -n "$X_USER" ]; then
    USER_ID=$(id -u $X_USER 2>/dev/null || echo "")
    if [ -n "$USER_ID" ]; then
        sudo -u $X_USER XDG_RUNTIME_DIR=/run/user/$USER_ID systemctl --user stop lswitch.service 2>/dev/null && echo "   ✓ Пользовательская служба остановлена" || true
    fi
fi

# Останавливаем GUI приложения
pkill -f "lswitch_control.py|lswitch-control" 2>/dev/null && echo "   ✓ GUI приложения остановлены" || true

echo -e "${YELLOW}📦 Установка зависимостей...${NC}"
run_or_log apt-get update -qq
run_or_log apt-get install -y python3-evdev xclip xdotool

echo -e "${YELLOW}📁 Копирование файлов...${NC}"
# Копируем основной скрипт
pref_install lswitch.py /usr/local/bin/lswitch

# Копируем модули
pref_install dictionary.py /usr/local/bin/dictionary.py
pref_install ngrams.py /usr/local/bin/ngrams.py
pref_install user_dictionary.py /usr/local/bin/user_dictionary.py
pref_install __version__.py /usr/local/bin/__version__.py

# Копируем адаптеры и утилиты
if [ -n "$PREFIX" ]; then
    LIB_DIR="$PREFIX/usr/local/lib/lswitch"
else
    LIB_DIR="/usr/local/lib/lswitch"
fi
mkdir -p "$LIB_DIR"
cp i18n.py "$LIB_DIR/i18n.py"
cp __version__.py "$LIB_DIR/__version__.py"
cp -r adapters "$LIB_DIR/"
cp -r utils "$LIB_DIR/"
chmod -R 755 "$LIB_DIR"

# GUI tray/control panel has been removed (see archive/removed_tray)

# Копируем иконку (программная генерация в runtime)
if [ -n "$PREFIX" ]; then
    mkdir -p "$PREFIX/usr/share/pixmaps"
    cp assets/lswitch.svg "$PREFIX/usr/share/pixmaps/lswitch.svg"
else
    install -Dm644 assets/lswitch.svg /usr/share/pixmaps/lswitch.svg
fi

# Desktop menu files for GUI were removed with the legacy tray. If you still need the desktop entry, find it in archive/removed_tray.
# Skipping installation of lswitch-control.desktop (legacy GUI removed)

# Legacy GUI removed: no autostart prompt
if [ "$TEST_MODE" -eq 1 ]; then
    echo "[TEST_MODE] Skipping GUI autostart (GUI removed)" | tee -a "$LOGFILE"
else
    echo "GUI tray is no longer installed by default. See archive/removed_tray for the legacy GUI implementation." 
fi

# Обновляем базу данных приложений
echo -e "${YELLOW}📋 Обновление базы данных приложений...${NC}"
if [ "$TEST_MODE" -eq 1 ]; then
    echo "[TEST_MODE] Skipping update-desktop-database" | tee -a "$LOGFILE"
else
    update-desktop-database /usr/share/applications/ 2>/dev/null && echo "   ✓ База данных приложений обновлена" || echo "   ⚠️  Не удалось обновить БД (опционально)"
fi

# Создаём директорию конфигурации
# Create user config directory
USER_CONFIG_DIR="/home/$X_USER/.config/lswitch"
if [ "$TEST_MODE" -eq 1 ]; then
    echo "[TEST_MODE] Creating user config dir $USER_CONFIG_DIR (no ownership changes)" | tee -a "$LOGFILE"
    mkdir -p "$USER_CONFIG_DIR"
else
    mkdir -p "$USER_CONFIG_DIR"
fi

# If system config exists from older installs, migrate it into user's config (only if user config is missing)
if [ -f /etc/lswitch/config.json ] && [ ! -f "$USER_CONFIG_DIR/config.json" ]; then
    echo "⚠️  Найден системный конфиг /etc/lswitch/config.json. Мигрируем в $USER_CONFIG_DIR/config.json"
    cp /etc/lswitch/config.json "$USER_CONFIG_DIR/config.json"
    chown $X_USER:$X_USER "$USER_CONFIG_DIR/config.json" 2>/dev/null || true
    echo "   ✓ Миграция завершена и системный конфиг помечен как устаревший."
    echo "   ⚠️  Внимание: /etc/lswitch/config.json устарел и будет игнорироваться в новых установках."
else
    if [ ! -f "$USER_CONFIG_DIR/config.json" ]; then
        cp config/config.json.example "$USER_CONFIG_DIR/config.json"
        chown $X_USER:$X_USER "$USER_CONFIG_DIR/config.json" 2>/dev/null || true
        echo "   ✓ Локальный конфиг создан: $USER_CONFIG_DIR/config.json"
    else
        echo "   ✓ Локальный конфиг уже существует: $USER_CONFIG_DIR/config.json"
    fi
fi

# Ensure /etc/lswitch exists for legacy compatibility but do not overwrite system configs by default
if [ "$TEST_MODE" -eq 1 ]; then
    echo "[TEST_MODE] Creating etc dir under prefix (no system /etc/lswitch changes)" | tee -a "$LOGFILE"
    mkdir -p "$PREFIX/etc/lswitch"
else
    mkdir -p /etc/lswitch
    chgrp input /etc/lswitch 2>/dev/null || true
fi

echo -e "${YELLOW}🔐 Настройка прав доступа (input devices)...${NC}"
# Устанавливаем udev правило для доступа к input устройствам
if [ "$TEST_MODE" -eq 1 ]; then
    echo "[TEST_MODE] Skipping udev rule copy and reload" | tee -a "$LOGFILE"
else
    install -Dm644 config/99-lswitch.rules /etc/udev/rules.d/99-lswitch.rules
    # Перезагружаем udev правила
    udevadm control --reload-rules
    udevadm trigger
fi

# Создаём группу input если её нет
if ! getent group input > /dev/null 2>&1; then
    groupadd -r input
    echo -e "   ✓ Группа input создана"
fi

echo -e "${YELLOW}⚙️  Установка systemd сервиса...${NC}"

# Определяем пользователя X-сессии
X_USER=$(detect_x_user)

if [ -z "$X_USER" ]; then
    echo -e "${RED}⚠️  Не удалось определить пользователя X-сессии${NC}"
    echo -e "   Укажите вручную в /etc/systemd/system/lswitch.service"
    X_USER="anton"
fi

echo -e "   Пользователь X-сессии: ${GREEN}$X_USER${NC}"

# Добавляем пользователя в группу input (для работы без root)
if [ "$TEST_MODE" -eq 1 ]; then
    echo "[TEST_MODE] Skipping usermod -a -G input $X_USER" | tee -a "$LOGFILE"
else
    usermod -a -G input $X_USER
    echo -e "   ✓ Пользователь $X_USER добавлен в группу 'input'"
    echo -e "   ${YELLOW}⚠️  ВАЖНО: Перелогиньтесь для применения прав!${NC}"
    echo
fi

X_AUTH="/home/$X_USER/.Xauthority"

# Копируем unit файл и подставляем переменные (заменяем любую строку Environment="XAUTHORITY=..." на значение для текущего пользователя)
if [ "$TEST_MODE" -eq 1 ]; then
    echo "[TEST_MODE] Skipping systemd unit install and daemon-reload" | tee -a "$LOGFILE"
else
    sed -e "s|^Environment=\"XAUTHORITY=.*\"|Environment=\"XAUTHORITY=$X_AUTH\"|" \
        config/lswitch.service > /etc/systemd/system/lswitch.service
    # Перезагружаем systemd
    systemctl daemon-reload
fi

echo
echo -e "${GREEN}✅ Установка завершена!${NC}"
echo
echo -e "${YELLOW}Управление сервисом (пользовательская служба):${NC}"
echo -e "  • Запустить:           systemctl --user start lswitch"
echo -e "  • Остановить:          systemctl --user stop lswitch"
echo -e "  • Перезапустить:       systemctl --user restart lswitch"
echo -e "  • Статус:              systemctl --user status lswitch"
echo -e "  • Включить автозапуск: ${GREEN}systemctl --user enable lswitch${NC}"
echo -e "  • Отключить автозапуск: systemctl --user disable lswitch"
echo
echo -e "${YELLOW}GUI Панель управления:${NC}"
echo -e "  lswitch-control  ${GREEN}(панель управления с поддержкой всех DE)${NC}"
echo
echo -e "${YELLOW}Логи:${NC}"
echo -e "  journalctl --user -u lswitch -f"
echo
echo -e "${YELLOW}Конфигурация:${NC}"
echo -e "  /etc/lswitch/config.json (системная)"
echo -e "  ~/.config/lswitch/user_dict.json (пользовательский словарь)"
echo
echo -e "${GREEN}Иконки меню:${NC} Используются системные темы Qt"
echo -e "${GREEN}Чекбоксы:${NC} Отображаются как иконки для выравнивания текста"
echo
# Autostart prompt and user-level systemd setup
if [ "$TEST_MODE" -eq 1 ]; then
    echo "[TEST_MODE] Skipping interactive autostart setup" | tee -a "$LOGFILE"
else
    read -p "Включить автозапуск при загрузке системы? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Копируем systemd unit в пользовательскую папку и включаем
        sudo -u $X_USER mkdir -p /home/$X_USER/.config/systemd/user
        cp /etc/systemd/system/lswitch.service /home/$X_USER/.config/systemd/user/
        chown $X_USER:$X_USER /home/$X_USER/.config/systemd/user/lswitch.service
        
        sudo -u $X_USER XDG_RUNTIME_DIR=/run/user/$(id -u $X_USER) systemctl --user daemon-reload
        sudo -u $X_USER XDG_RUNTIME_DIR=/run/user/$(id -u $X_USER) systemctl --user enable lswitch
        sudo -u $X_USER XDG_RUNTIME_DIR=/run/user/$(id -u $X_USER) systemctl --user start lswitch
        
        echo -e "${GREEN}✅ Автозапуск включён и сервис запущен!${NC}"
        echo -e "${YELLOW}Проверьте статус: systemctl --user status lswitch${NC}"
    else
        echo -e "${YELLOW}Сервис установлен, но не запущен.${NC}"
        echo -e "Запустите вручную: ${GREEN}systemctl --user start lswitch${NC}"
    fi
fi

echo
