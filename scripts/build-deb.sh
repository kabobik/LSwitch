#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# LSwitch — сборка .deb пакета
#
# Использование:
#   bash scripts/build-deb.sh
#
# Результат:
#   build/lswitch_<version>_all.deb
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Читаем версию из __version__.py
VERSION=$(python3 -c "exec(open('$PROJECT_DIR/__version__.py').read()); print(__version__)")
PACKAGE="lswitch"
ARCH="all"
DEB_NAME="${PACKAGE}_${VERSION}_${ARCH}"

BUILD_DIR="$PROJECT_DIR/build"
PKG_DIR="$BUILD_DIR/$DEB_NAME"

echo "Сборка $PACKAGE $VERSION..."

# ─── Очистка ───────────────────────────────────────────────────
# После dpkg -i файлы в build/ могут принадлежать root
if [ -d "$PKG_DIR" ]; then
    rm -rf "$PKG_DIR" 2>/dev/null || sudo rm -rf "$PKG_DIR"
fi
rm -f "$BUILD_DIR/${DEB_NAME}.deb" 2>/dev/null || true

# ─── Структура .deb ───────────────────────────────────────────
# Python пакет → /usr/lib/lswitch/
INSTALL_ROOT="$PKG_DIR/usr/lib/$PACKAGE"
mkdir -p "$INSTALL_ROOT"
cp -r "$PROJECT_DIR/lswitch"       "$INSTALL_ROOT/lswitch"
cp    "$PROJECT_DIR/__version__.py" "$INSTALL_ROOT/__version__.py"
find "$INSTALL_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Entry point → /usr/bin/lswitch
mkdir -p "$PKG_DIR/usr/bin"
cat > "$PKG_DIR/usr/bin/$PACKAGE" << 'ENTRY'
#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, "/usr/lib/lswitch")
from lswitch.cli import main
sys.exit(main())
ENTRY
chmod +x "$PKG_DIR/usr/bin/$PACKAGE"

# systemd user unit → /usr/lib/systemd/user/
mkdir -p "$PKG_DIR/usr/lib/systemd/user"
cp "$PROJECT_DIR/config/lswitch.service" "$PKG_DIR/usr/lib/systemd/user/"

# udev rules → /etc/udev/rules.d/
mkdir -p "$PKG_DIR/etc/udev/rules.d"
cp "$PROJECT_DIR/config/99-lswitch.rules" "$PKG_DIR/etc/udev/rules.d/"

# .desktop → /usr/share/applications/
mkdir -p "$PKG_DIR/usr/share/applications"
cp "$PROJECT_DIR/config/lswitch-control.desktop" "$PKG_DIR/usr/share/applications/"

# Иконка SVG → /usr/share/icons/hicolor/scalable/apps/
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/scalable/apps"
cp "$PROJECT_DIR/assets/lswitch.svg" "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/$PACKAGE.svg"

# ─── DEBIAN control ───────────────────────────────────────────
mkdir -p "$PKG_DIR/DEBIAN"

cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.10), python3-evdev, python3-xlib, python3-pyudev
Recommends: python3-pyqt5
Maintainer: Anton <anton@localhost>
Homepage: https://github.com/kabobik/lswitch
Description: Keyboard layout switcher with auto-conversion
 LSwitch intercepts keyboard events via evdev and converts
 text between EN/RU layouts on double-Shift press.
 Features auto-detection, self-learning dictionary, and
 system tray GUI.
EOF

# postinst — обновить udev и показать per-user шаги
cat > "$PKG_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/sh
set -e

# Перезагрузить udev правила
udevadm control --reload-rules 2>/dev/null || true
udevadm trigger 2>/dev/null || true

# Обновить кэш иконок
gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true

echo ""
echo "LSwitch установлен!"
echo ""
echo "  1. Добавьте себя в группу input:  sudo usermod -a -G input \$USER"
echo "  2. Перелогиньтесь"
echo "  3. Запустите GUI: lswitch"
echo ""
echo "  Headless без иконки в трее (опционально):"
echo "      systemctl --user enable --now lswitch"
echo ""
echo "  Не запускайте GUI и headless-сервис одновременно."
echo ""
EOF
chmod +x "$PKG_DIR/DEBIAN/postinst"

# postrm — очистить при удалении
cat > "$PKG_DIR/DEBIAN/postrm" << 'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    gtk-update-icon-cache /usr/share/icons/hicolor 2>/dev/null || true
fi
EOF
chmod +x "$PKG_DIR/DEBIAN/postrm"

# ─── Права ─────────────────────────────────────────────────────
find "$PKG_DIR" -type d -exec chmod 755 {} +
find "$PKG_DIR" -type f -exec chmod 644 {} +
chmod +x "$PKG_DIR/usr/bin/$PACKAGE"
chmod +x "$PKG_DIR/DEBIAN/postinst"
chmod +x "$PKG_DIR/DEBIAN/postrm"

# ─── Сборка ───────────────────────────────────────────────────
dpkg-deb --build --root-owner-group "$PKG_DIR" "$BUILD_DIR/${DEB_NAME}.deb"

echo ""
echo "Готово: $BUILD_DIR/${DEB_NAME}.deb"
echo ""
echo "Установка:  sudo dpkg -i $BUILD_DIR/${DEB_NAME}.deb"
echo "            sudo apt install -f  # если нужны зависимости"
echo "Удаление:   sudo apt remove $PACKAGE"
