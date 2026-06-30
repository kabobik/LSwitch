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
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="$DATA_HOME/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
SYSTEMD_DIR="$CONFIG_HOME/systemd/user"
AUTOSTART_DIR="$CONFIG_HOME/autostart"
DESKTOP_DIR="$DATA_HOME/applications"
ICON_THEME_DIR="$DATA_HOME/icons/hicolor"
ICON_DIR="$ICON_THEME_DIR/scalable/apps"
LEGACY_ICON_DIR="$HOME/.icons"
UDEV_RULES="/etc/udev/rules.d/99-lswitch.rules"
CURRENT_USER="${USER:-$(id -un)}"

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

# ─── Дистрибутивы и системные пакеты ───────────────────────────
detect_pkg_manager() {
    if command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v pacman &>/dev/null; then
        echo "pacman"
    else
        echo ""
    fi
}

package_for_dependency() {
    local manager="$1"
    local dep="$2"

    case "$manager:$dep" in
        apt:evdev)          echo "python3-evdev" ;;
        apt:xlib)           echo "python3-xlib" ;;
        apt:pyudev)         echo "python3-pyudev" ;;
        apt:pyqt6_qtdbus)   echo "python3-pyqt6" ;;
        apt:wl_clipboard)   echo "wl-clipboard" ;;
        apt:qt6_wayland)    echo "qt6-wayland" ;;

        pacman:evdev)        echo "python-evdev" ;;
        pacman:xlib)         echo "python-xlib" ;;
        pacman:pyudev)       echo "python-pyudev" ;;
        pacman:pyqt6_qtdbus) echo "python-pyqt6" ;;
        pacman:wl_clipboard) echo "wl-clipboard" ;;
        pacman:qt6_wayland)  echo "qt6-wayland" ;;
    esac
}

add_unique_pkg() {
    local -n target_array="$1"
    local pkg="$2"
    local existing

    [ -n "$pkg" ] || return 0
    for existing in "${target_array[@]}"; do
        [ "$existing" = "$pkg" ] && return 0
    done
    target_array+=("$pkg")
}

add_dep_pkg() {
    local target_array_name="$1"
    local manager="$2"
    local dep="$3"
    local pkg

    pkg="$(package_for_dependency "$manager" "$dep")"
    add_unique_pkg "$target_array_name" "$pkg"
}

install_system_packages() {
    local manager="$1"
    shift

    [ "$#" -gt 0 ] || return 0

    case "$manager" in
        apt)
            info "Установка системных пакетов через apt: $*"
            sudo apt-get install -y "$@"
            ;;
        pacman)
            info "Установка системных пакетов через pacman: $*"
            sudo pacman -S --needed --noconfirm "$@"
            ;;
        *)
            error "Поддерживаются apt и pacman. Установите вручную: $*"
            exit 1
            ;;
    esac
}

is_wayland_session() {
    [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]
}

check_python_import() {
    local module="$1"
    python3 -c "import importlib; importlib.import_module('$module')" 2>/dev/null
}

ensure_input_group() {
    if getent group input &>/dev/null; then
        return 0
    fi

    info "Создание группы input (потребуется пароль)..."
    sudo groupadd -r input
}

detect_desktop_environment() {
    local desktop
    desktop="$(
        printf '%s:%s:%s:%s' \
            "${XDG_CURRENT_DESKTOP:-}" \
            "${DESKTOP_SESSION:-}" \
            "${GDMSESSION:-}" \
            "${KDE_FULL_SESSION:-}" |
        tr '[:upper:]' '[:lower:]'
    )"

    if [ -n "${KDE_FULL_SESSION:-}" ] || [[ "$desktop" == *kde* ]] || [[ "$desktop" == *plasma* ]]; then
        echo "KDE Plasma"
    elif [[ "$desktop" == *cinnamon* ]]; then
        echo "Cinnamon"
    elif [[ "$desktop" == *gnome* ]]; then
        echo "GNOME"
    else
        echo "XDG-compatible desktop"
    fi
}

# ─── Удаление ─────────────────────────────────────────────────
remove() {
    info "Удаление LSwitch..."

    # Остановить и отключить legacy user-service
    systemctl --user stop "$APP_NAME" 2>/dev/null || true
    systemctl --user disable "$APP_NAME" 2>/dev/null || true

    # Удалить файлы
    rm -rf "$INSTALL_DIR"
    rm -f  "$BIN_DIR/$APP_NAME"
    rm -f  "$SYSTEMD_DIR/$APP_NAME.service"
    rm -f  "$AUTOSTART_DIR/lswitch-control.desktop"
    rm -f  "$DESKTOP_DIR/lswitch-control.desktop"
    rm -f  "$ICON_DIR/$APP_NAME.svg"
    rm -f  "$LEGACY_ICON_DIR/$APP_NAME.svg"

    systemctl --user daemon-reload 2>/dev/null || true
    refresh_desktop_integration

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
    local pkg_manager
    local packages=()
    local missing=()
    local needs_install=false

    # Python 3.11+
    if ! command -v python3 &>/dev/null; then
        error "Python3 не найден"
        exit 1
    fi
    local py_ver
    py_ver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local py_major py_minor
    py_major=$(echo "$py_ver" | cut -d. -f1)
    py_minor=$(echo "$py_ver" | cut -d. -f2)
    if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt 11 ]; }; then
        error "Требуется Python 3.11+, найден $py_ver"
        exit 1
    fi
    ok "Python $py_ver"

    # Проверяем Python-модули
    pkg_manager="$(detect_pkg_manager)"

    if ! check_python_import "evdev"; then
        missing+=("evdev")
        needs_install=true
        add_dep_pkg packages "$pkg_manager" "evdev"
    fi
    if ! check_python_import "Xlib"; then
        missing+=("python-xlib")
        needs_install=true
        add_dep_pkg packages "$pkg_manager" "xlib"
    fi
    if ! check_python_import "pyudev"; then
        missing+=("pyudev")
        needs_install=true
        add_dep_pkg packages "$pkg_manager" "pyudev"
    fi
    if ! check_python_import "PyQt6.QtDBus"; then
        missing+=("PyQt6.QtDBus")
        needs_install=true
        add_dep_pkg packages "$pkg_manager" "pyqt6_qtdbus"
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        warn "Отсутствуют Python-модули: ${missing[*]}"
    fi

    if ! command -v wl-copy &>/dev/null || ! command -v wl-paste &>/dev/null; then
        warn "wl-clipboard не найден — Wayland selection fallback будет недоступен"
        needs_install=true
        add_dep_pkg packages "$pkg_manager" "wl_clipboard"
    fi

    if is_wayland_session; then
        add_dep_pkg packages "$pkg_manager" "qt6_wayland"
    fi

    if [ "$needs_install" = true ] && [ -z "$pkg_manager" ]; then
        error "Не найден поддерживаемый пакетный менеджер. Поддерживаются apt и pacman."
        exit 1
    fi

    install_system_packages "$pkg_manager" "${packages[@]}"

    # Повторная проверка после установки пакетов.
    for mod in evdev Xlib pyudev PyQt6.QtDBus; do
        if ! check_python_import "$mod"; then
            error "Python-модуль всё ещё недоступен после установки: $mod"
            exit 1
        fi
    done
    if ! command -v wl-copy &>/dev/null || ! command -v wl-paste &>/dev/null; then
        error "wl-copy/wl-paste всё ещё недоступны после установки wl-clipboard"
        exit 1
    fi

    ok "Зависимости в порядке"
}

install_desktop_file() {
    local target="$1"
    local exec_cmd="$2"
    local mode="${3:-menu}"

    cp "$PROJECT_DIR/config/lswitch-control.desktop" "$target"
    set_desktop_key "$target" "Exec" "$exec_cmd"
    set_desktop_key "$target" "TryExec" "$BIN_DIR/$APP_NAME"

    if [ "$mode" = "autostart" ]; then
        set_desktop_key "$target" "Hidden" "false"
        set_desktop_key "$target" "X-GNOME-Autostart-enabled" "true"
        set_desktop_key "$target" "X-KDE-autostart-after" "panel"
    fi

    chmod 644 "$target"
    validate_desktop_file "$target"
}

set_desktop_key() {
    local file="$1"
    local key="$2"
    local value="$3"
    local escaped

    escaped="${value//\\/\\\\}"
    escaped="${escaped//&/\\&}"
    escaped="${escaped//|/\\|}"

    if grep -q "^$key=" "$file"; then
        sed -i "s|^$key=.*|$key=$escaped|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
}

validate_desktop_file() {
    local file="$1"

    if command -v desktop-file-validate &>/dev/null; then
        if ! desktop-file-validate "$file"; then
            error "Некорректный desktop-файл: $file"
            exit 1
        fi
    fi
}

refresh_desktop_integration() {
    info "Обновление меню и кэша иконок..."

    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    fi
    if command -v xdg-desktop-menu &>/dev/null; then
        xdg-desktop-menu forceupdate --mode user >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache &>/dev/null; then
        gtk-update-icon-cache -q -t -f "$ICON_THEME_DIR" >/dev/null 2>&1 || true
    fi
    if command -v xdg-icon-resource &>/dev/null; then
        xdg-icon-resource forceupdate --theme hicolor >/dev/null 2>&1 || true
    fi
    if command -v kbuildsycoca6 &>/dev/null; then
        kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
    elif command -v kbuildsycoca5 &>/dev/null; then
        kbuildsycoca5 --noincremental >/dev/null 2>&1 || true
    fi

    ok "Меню и кэш иконок обновлены"
}

verify_desktop_integration() {
    local autostart_expected="${1:-false}"
    local menu_file="$DESKTOP_DIR/lswitch-control.desktop"
    local autostart_file="$AUTOSTART_DIR/lswitch-control.desktop"

    [ -f "$menu_file" ] || { error "Не создан ярлык меню: $menu_file"; exit 1; }
    grep -Fxq "Exec=$BIN_DIR/$APP_NAME" "$menu_file" || {
        error "В ярлыке меню неверный Exec: $menu_file"
        exit 1
    }
    [ -f "$ICON_DIR/$APP_NAME.svg" ] || { error "Не установлена иконка: $ICON_DIR/$APP_NAME.svg"; exit 1; }

    if [ "$autostart_expected" = "true" ]; then
        [ -f "$autostart_file" ] || { error "Не создан GUI автозапуск: $autostart_file"; exit 1; }
        grep -Fxq "Exec=$BIN_DIR/$APP_NAME --replace" "$autostart_file" || {
            error "В автозапуске неверный Exec: $autostart_file"
            exit 1
        }
        grep -Fxq "Hidden=false" "$autostart_file" || {
            error "Автозапуск отключён через Hidden=true/нет Hidden=false: $autostart_file"
            exit 1
        }
    fi

    ok "Интеграция с рабочим столом проверена"
}

disable_legacy_service() {
    info "Отключение legacy systemd сервиса..."
    systemctl --user stop "$APP_NAME" 2>/dev/null || true
    systemctl --user disable "$APP_NAME" 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/$APP_NAME.service"
    systemctl --user daemon-reload 2>/dev/null || true
    ok "Systemd автозапуск отключён"
}

enable_gui_autostart() {
    mkdir -p "$AUTOSTART_DIR"
    install_desktop_file "$AUTOSTART_DIR/lswitch-control.desktop" "$BIN_DIR/$APP_NAME --replace" "autostart"
    ok "GUI автозапуск включён: $AUTOSTART_DIR/lswitch-control.desktop"
}

disable_gui_autostart() {
    rm -f "$AUTOSTART_DIR/lswitch-control.desktop"
    ok "GUI автозапуск отключён"
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
    info "Окружение рабочего стола: $(detect_desktop_environment)"
    check_deps

    # 2. Копирование приложения
    info "Копирование файлов в $INSTALL_DIR..."
    info "Источник установки: $PROJECT_DIR"
    mkdir -p "$INSTALL_DIR"
    # Копируем пакет и метаданные
    rm -rf "$INSTALL_DIR/lswitch" "$INSTALL_DIR/__version__.py" "$INSTALL_DIR/setup.py"
    cp -r "$PROJECT_DIR/lswitch"       "$INSTALL_DIR/lswitch"
    cp    "$PROJECT_DIR/__version__.py" "$INSTALL_DIR/__version__.py"
    # Удаляем __pycache__ из копии
    find "$INSTALL_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

    if ! grep -q "config.toml" "$INSTALL_DIR/lswitch/config.py"; then
        error "Установленная копия не содержит TOML config loader: $INSTALL_DIR/lswitch/config.py"
        error "Проверьте, что install.sh запущен из актуальной папки проекта: $PROJECT_DIR"
        exit 1
    fi
    ok "Файлы скопированы"

    # 3. Entry point
    info "Создание команды $APP_NAME..."
    mkdir -p "$BIN_DIR"
    install_dir_py="$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$INSTALL_DIR")"
    cat > "$BIN_DIR/$APP_NAME" << ENTRY
#!/usr/bin/env python3
import sys

# Добавляем директорию установки в путь.
# Путь фиксируется на момент install, чтобы runtime XDG_DATA_HOME не уводил
# импорт в старую копию пакета.
install_dir = $install_dir_py
if install_dir not in sys.path:
    sys.path.insert(0, install_dir)

from lswitch.cli import main
sys.exit(main())
ENTRY
    chmod +x "$BIN_DIR/$APP_NAME"
    ok "Команда: $BIN_DIR/$APP_NAME"

    # 4. Legacy systemd cleanup
    disable_legacy_service

    # 5. Иконка
    info "Установка иконки..."
    mkdir -p "$ICON_DIR"
    mkdir -p "$LEGACY_ICON_DIR"
    cp "$PROJECT_DIR/assets/lswitch.svg" "$ICON_DIR/$APP_NAME.svg"
    cp "$PROJECT_DIR/assets/lswitch.svg" "$LEGACY_ICON_DIR/$APP_NAME.svg"
    ok "Иконка установлена"

    # 6. .desktop файл
    info "Установка ярлыка в меню приложений..."
    mkdir -p "$DESKTOP_DIR"
    install_desktop_file "$DESKTOP_DIR/lswitch-control.desktop" "$BIN_DIR/$APP_NAME" "menu"
    ok "Ярлык установлен"

    # 7. udev правила (нужен sudo)
    ensure_input_group
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
    if ! groups "$CURRENT_USER" | grep -qw input; then
        info "Добавление в группу input (потребуется пароль)..."
        sudo usermod -a -G input "$CURRENT_USER"
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
    echo "  Запуск:         $BIN_DIR/$APP_NAME"
    echo "  Перезапуск:     $BIN_DIR/$APP_NAME --replace"
    echo "  GUI автозапуск: $AUTOSTART_DIR/lswitch-control.desktop"
    echo "  Удаление:       bash scripts/install.sh --remove"
    echo ""

    # Предложить включить автозапуск
    read -rp "Включить GUI автозапуск при входе в сеанс? [Y/n] " answer
    answer="${answer:-y}"
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        enable_gui_autostart
        refresh_desktop_integration
        verify_desktop_integration "true"
    else
        disable_gui_autostart
        refresh_desktop_integration
        verify_desktop_integration "false"
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
