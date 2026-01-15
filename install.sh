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
apt-get update -qq
apt-get install -y python3-evdev python3-pyqt5 xclip xdotool

echo -e "${YELLOW}📁 Копирование файлов...${NC}"
# Копируем основной скрипт
install -m 755 lswitch.py /usr/local/bin/lswitch

# Копируем модули
install -m 644 dictionary.py /usr/local/bin/dictionary.py
install -m 644 ngrams.py /usr/local/bin/ngrams.py
install -m 644 user_dictionary.py /usr/local/bin/user_dictionary.py
install -m 644 __version__.py /usr/local/bin/__version__.py

# Копируем адаптеры и утилиты
mkdir -p /usr/local/lib/lswitch
cp i18n.py /usr/local/lib/lswitch/i18n.py
cp __version__.py /usr/local/lib/lswitch/__version__.py
cp -r adapters /usr/local/lib/lswitch/
cp -r utils /usr/local/lib/lswitch/
chmod -R 755 /usr/local/lib/lswitch

# Копируем GUI панель управления (lswitch-control)
install -m 755 lswitch_control.py /usr/local/bin/lswitch-control

# Копируем иконку (программная генерация в runtime)
install -Dm644 assets/lswitch.svg /usr/share/pixmaps/lswitch.svg

# Копируем .desktop файл для системного меню
install -Dm644 config/lswitch-control.desktop /usr/share/applications/lswitch-control.desktop
# Админский лаунчер не устанавливаем в системное меню по умолчанию
# Админ-панель доступна только через секретный триггер (5 кликов по заголовку меню) и запускается через pkexec
# (Если всё же нужно установить админский лаунчер вручную, выполните: install -Dm644 config/lswitch-control-admin.desktop /usr/share/applications/lswitch-control-admin.desktop)

# Предложим включить автозапуск GUI панели для пользователя X-сессии
# Если скрипт не интерактивен, просто выведем инструкцию
if [ -t 0 ]; then
    read -p "Включить автозапуск GUI панели для пользователя $X_USER? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo -u $X_USER mkdir -p /home/$X_USER/.config/autostart
        sudo -u $X_USER cp /usr/share/applications/lswitch-control.desktop /home/$X_USER/.config/autostart/lswitch-control.desktop
        chown $X_USER:$X_USER /home/$X_USER/.config/autostart/lswitch-control.desktop 2>/dev/null || true
        echo "   ✓ Автозапуск GUI включён для $X_USER"
    else
        echo "   Автозапуск GUI не включён"
    fi
else
    echo "Для включения автозапуска GUI выполните (под пользователем):"
    echo "  mkdir -p ~/.config/autostart && cp /usr/share/applications/lswitch-control.desktop ~/.config/autostart/"
fi

# Обновляем базу данных приложений
echo -e "${YELLOW}📋 Обновление базы данных приложений...${NC}"
update-desktop-database /usr/share/applications/ 2>/dev/null && echo "   ✓ База данных приложений обновлена" || echo "   ⚠️  Не удалось обновить БД (опционально)"

# Создаём директорию конфигурации
# Create user config directory
USER_CONFIG_DIR="/home/$X_USER/.config/lswitch"
mkdir -p "$USER_CONFIG_DIR"

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
mkdir -p /etc/lswitch
chgrp input /etc/lswitch 2>/dev/null || true

echo -e "${YELLOW}🔐 Настройка прав доступа (input devices)...${NC}"
# Устанавливаем udev правило для доступа к input устройствам
install -Dm644 config/99-lswitch.rules /etc/udev/rules.d/99-lswitch.rules

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
X_USER=$(detect_x_user)

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

# Копируем unit файл и подставляем переменные (заменяем любую строку Environment="XAUTHORITY=..." на значение для текущего пользователя)
sed -e "s|^Environment=\"XAUTHORITY=.*\"|Environment=\"XAUTHORITY=$X_AUTH\"|" \
    config/lswitch.service > /etc/systemd/system/lswitch.service

# Перезагружаем systemd
systemctl daemon-reload

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
echo
