#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# LSwitch — установка для пользователя
#
# Использование:
#   bash scripts/install.sh          — установить
#   bash scripts/install.sh --remove — удалить
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

APP_NAME="lswitch"
VERSION="2.0.0"

# Пути установки
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
SYSTEMD_DIR="$HOME/.config/systemd/user"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
UDEV_RULES="/etc/udev/rules.d/99-lswitch.rules"

# Определяем корень проекта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ─── Цвета ────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ─── Удаление ─────────────────────────────────────────────────
remove() {
    info "Удаление LSwitch..."

    # Остановить и отключить сервис
    systemctl --user stop "$APP_NAME" 2>/dev/null || true
    systemctl --user disable "$APP_NAME" 2>/dev/null || true

    # Удалить файлы
    rm -rf "$INSTALL_DIR"
    rm -f  "$BIN_DIR/$APP_NAME"
    rm -f  "$SYSTEMD_DIR/$APP_NAME.service"
    rm -f  "$DESKTOP_DIR/lswitch-control.desktop"
    rm -f  "$ICON_DIR/$APP_NAME.svg"

    systemctl --user daemon-reload 2>/dev/null || true

    # udev — требует sudo
    if [ -f "$UDEV_RULES" ]; then
        info "Удаление udev правил (потребуется пароль)..."
        sudo rm -f "$UDEV_RULES"
        sudo udevadm control --reload-rules 2>/dev/null || true
    fi

    ok "LSwitch удалён"
    exit 0
}

# ─── Проверка зависимостей ─────────────────────────────────────
check_deps() {
    local missing=()

    # Python 3.10+
    if ! command -v python3 &>/dev/null; then
        error "Python3 не найден"
        exit 1
    fi
    local py_ver
    py_ver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local py_major py_minor
    py_major=$(echo "$py_ver" | cut -d. -f1)
    py_minor=$(echo "$py_ver" | cut -d. -f2)
    if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt 10 ]; }; then
        error "Требуется Python 3.10+, найден $py_ver"
        exit 1
    fi
    ok "Python $py_ver"

    # Проверяем Python-модули
    for mod in evdev Xlib pyudev; do
        if ! python3 -c "import $mod" 2>/dev/null; then
            missing+=("$mod")
        fi
    done

    # PyQt5 (не блокируем, но предупреждаем)
    local has_qt=true
    if ! python3 -c "import PyQt5" 2>/dev/null; then
        has_qt=false
    fi

    # Если чего-то не хватает — пробуем apt
    if [ ${#missing[@]} -gt 0 ]; then
        warn "Отсутствуют Python-модули: ${missing[*]}"

        if command -v apt &>/dev/null; then
            info "Попытка установить через apt..."
            local apt_pkgs=()
            for mod in "${missing[@]}"; do
                case "$mod" in
                    evdev)  apt_pkgs+=("python3-evdev") ;;
                    Xlib)   apt_pkgs+=("python3-xlib") ;;
                    pyudev) apt_pkgs+=("python3-pyudev") ;;
                esac
            done
            if [ ${#apt_pkgs[@]} -gt 0 ]; then
                sudo apt install -y "${apt_pkgs[@]}"
            fi
        else
            error "apt не найден. Установите вручную: ${missing[*]}"
            exit 1
        fi
    fi

    if [ "$has_qt" = false ]; then
        warn "PyQt5 не найден — GUI (иконка в трее) будет недоступен"
        info "Установить: sudo apt install python3-pyqt5"
    fi

    ok "Зависимости в порядке"
}

# ─── Установка ─────────────────────────────────────────────────
install() {
    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║   LSwitch $VERSION — установка        ║"
    echo "╚══════════════════════════════════════╝"
    echo ""

    # 1. Проверка зависимостей
    info "Проверка зависимостей..."
    check_deps

    # 2. Копирование приложения
    info "Копирование файлов в $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    # Копируем пакет и метаданные
    rm -rf "$INSTALL_DIR/lswitch" "$INSTALL_DIR/__version__.py" "$INSTALL_DIR/setup.py"
    cp -r "$PROJECT_DIR/lswitch"       "$INSTALL_DIR/lswitch"
    cp    "$PROJECT_DIR/__version__.py" "$INSTALL_DIR/__version__.py"
    # Удаляем __pycache__ из копии
    find "$INSTALL_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    ok "Файлы скопированы"

    # 3. Entry point
    info "Создание команды $APP_NAME..."
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/$APP_NAME" << 'ENTRY'
#!/usr/bin/env python3
import sys
import os

# Добавляем директорию установки в путь
install_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "lswitch")
if install_dir not in sys.path:
    sys.path.insert(0, install_dir)

from lswitch.cli import main
sys.exit(main())
ENTRY
    chmod +x "$BIN_DIR/$APP_NAME"
    ok "Команда: $BIN_DIR/$APP_NAME"

    # 4. systemd unit
    info "Установка systemd сервиса..."
    mkdir -p "$SYSTEMD_DIR"
    cp "$PROJECT_DIR/config/lswitch.service" "$SYSTEMD_DIR/$APP_NAME.service"
    systemctl --user daemon-reload
    ok "Сервис установлен"

    # 5. Иконка
    info "Установка иконки..."
    mkdir -p "$ICON_DIR"
    cp "$PROJECT_DIR/assets/lswitch.svg" "$ICON_DIR/$APP_NAME.svg"
    ok "Иконка установлена"

    # 6. .desktop файл
    info "Установка ярлыка в меню приложений..."
    mkdir -p "$DESKTOP_DIR"
    cp "$PROJECT_DIR/config/lswitch-control.desktop" "$DESKTOP_DIR/"
    ok "Ярлык установлен"

    # 7. udev правила (нужен sudo)
    if [ ! -f "$UDEV_RULES" ]; then
        info "Установка udev правил (потребуется пароль)..."
        sudo cp "$PROJECT_DIR/config/99-lswitch.rules" "$UDEV_RULES"
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        ok "udev правила установлены"
    else
        ok "udev правила уже на месте"
    fi

    # 8. Группа input
    if ! groups "$USER" | grep -qw input; then
        info "Добавление в группу input (потребуется пароль)..."
        sudo usermod -a -G input "$USER"
        warn "Перелогиньтесь для применения прав группы input"
    else
        ok "Пользователь уже в группе input"
    fi

    # 9. Проверяем что $BIN_DIR в PATH
    if ! echo "$PATH" | grep -q "$BIN_DIR"; then
        warn "$BIN_DIR не в PATH. Добавьте в ~/.bashrc:"
        echo "       export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi

    echo ""
    echo "╔══════════════════════════════════════╗"
    echo "║   Установка завершена!               ║"
    echo "╚══════════════════════════════════════╝"
    echo ""
    echo "  Запуск:       $APP_NAME"
    echo "  Автозапуск:   systemctl --user enable --now $APP_NAME"
    echo "  Статус:       systemctl --user status $APP_NAME"
    echo "  Удаление:     bash scripts/install.sh --remove"
    echo ""

    # Предложить включить автозапуск
    read -rp "Включить автозапуск? [Y/n] " answer
    answer="${answer:-y}"
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        systemctl --user enable --now "$APP_NAME"
        ok "Автозапуск включён, сервис запущен"
    fi
}

# ─── Точка входа ───────────────────────────────────────────────
case "${1:-}" in
    --remove|--uninstall|remove|uninstall)
        remove
        ;;
    --help|-h)
        echo "Использование: bash $0 [--remove]"
        echo ""
        echo "  (без аргументов)  — установить LSwitch"
        echo "  --remove          — полностью удалить LSwitch"
        ;;
    *)
        install
        ;;
esac
