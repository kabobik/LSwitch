#!/bin/bash
# Скрипт сборки пакетов LSwitch для различных дистрибутивов

set -e

VERSION="1.1.0"
PACKAGE_NAME="lswitch"
BUILD_DIR="build"
MAINTAINER="Anton <anton@example.com>"

# Цвета
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   LSwitch - Сборка пакетов             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo

# Очистка предыдущей сборки
if [ -d "$BUILD_DIR" ]; then
    echo -e "${YELLOW}🗑️  Очистка предыдущей сборки...${NC}"
    rm -rf "$BUILD_DIR"
fi

mkdir -p "$BUILD_DIR"

# Функция сборки DEB пакета
build_deb() {
    echo -e "${GREEN}📦 Сборка DEB пакета...${NC}"
    
    DEB_DIR="$BUILD_DIR/${PACKAGE_NAME}_${VERSION}_all"
    mkdir -p "$DEB_DIR/DEBIAN"
    
    # Создаём структуру каталогов
    mkdir -p "$DEB_DIR/usr/local/bin"
    mkdir -p "$DEB_DIR/usr/local/lib/lswitch/adapters"
    mkdir -p "$DEB_DIR/usr/local/lib/lswitch/utils"
    mkdir -p "$DEB_DIR/etc/lswitch"
    mkdir -p "$DEB_DIR/usr/share/applications"
    mkdir -p "$DEB_DIR/usr/share/icons/hicolor/scalable/apps"
    
    # Копируем файлы
    cp lswitch.py "$DEB_DIR/usr/local/bin/lswitch"
    cp lswitch_control.py "$DEB_DIR/usr/local/bin/lswitch-control"
    cp dictionary.py "$DEB_DIR/usr/local/bin/"
    cp ngrams.py "$DEB_DIR/usr/local/bin/"
    cp user_dictionary.py "$DEB_DIR/usr/local/bin/"
    cp i18n.py "$DEB_DIR/usr/local/bin/"
    chmod +x "$DEB_DIR/usr/local/bin/lswitch"
    chmod +x "$DEB_DIR/usr/local/bin/lswitch-control"
    
    # Адаптеры
    cp adapters/*.py "$DEB_DIR/usr/local/lib/lswitch/adapters/"
    
    # Утилиты
    cp utils/*.py "$DEB_DIR/usr/local/lib/lswitch/utils/"
    
    # Конфигурация
    cp config/config.json.example "$DEB_DIR/etc/lswitch/config.json"
    
    # Desktop файл
    cp config/lswitch-control.desktop "$DEB_DIR/usr/share/applications/"
    
    # udev правила
    mkdir -p "$DEB_DIR/etc/udev/rules.d"
    cp config/99-lswitch.rules "$DEB_DIR/etc/udev/rules.d/" 2>/dev/null || true
    
    # Иконка (если есть)
    if [ -f "assets/lswitch.svg" ]; then
        cp assets/lswitch.svg "$DEB_DIR/usr/share/icons/hicolor/scalable/apps/"
    fi
    
    # Создаём control файл
    cat > "$DEB_DIR/DEBIAN/control" << EOF
Package: $PACKAGE_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-evdev, python3-pyqt5, xclip, xdotool
Maintainer: $MAINTAINER
Description: Automatic keyboard layout switcher for Linux
 LSwitch automatically switches keyboard layouts based on typed text.
 Features:
  - Double Shift to convert last word
  - Auto-conversion of mistyped words
  - Self-learning dictionary
  - System tray GUI control panel
  - Support for KDE and Cinnamon desktop environments
Homepage: https://github.com/yourusername/lswitch
EOF
    
    # Создаём postinst скрипт (выполняется после установки)
    cat > "$DEB_DIR/DEBIAN/postinst" << 'EOF'
#!/bin/bash
set -e

# Получаем пользователя X-сессии
X_USER=$(who | grep -E "\(:0\)" | awk '{print $1}' | head -n1)
if [ -z "$X_USER" ]; then
    X_USER=$(logname 2>/dev/null || echo "$SUDO_USER")
fi

# Добавляем пользователя в группу input
if [ -n "$X_USER" ]; then
    usermod -a -G input "$X_USER" 2>/dev/null || true
    echo "✓ Пользователь $X_USER добавлен в группу 'input'"
fi

# Создаём systemd unit файл для пользователя
if [ -n "$X_USER" ]; then
    USER_HOME=$(eval echo ~$X_USER)
    SYSTEMD_DIR="$USER_HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"
    
    cat > "$SYSTEMD_DIR/lswitch.service" << EOFSERVICE
[Unit]
Description=LSwitch - Layout Switcher (evdev)
Documentation=https://github.com/yourusername/lswitch
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 -u /usr/local/bin/lswitch
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOFSERVICE
    
    chown -R "$X_USER:$X_USER" "$SYSTEMD_DIR"
    echo "✓ Systemd unit создан: $SYSTEMD_DIR/lswitch.service"
fi

echo "✓ Установка завершена!"
echo
echo "Для запуска службы выполните:"
echo "  systemctl --user start lswitch"
echo "  systemctl --user enable lswitch  # для автозапуска"
echo
echo "Для запуска GUI панели:"
echo "  lswitch-control"
echo
echo "⚠️  ВАЖНО: Перелогиньтесь для применения прав группы 'input'!"

exit 0
EOF
    
    chmod 755 "$DEB_DIR/DEBIAN/postinst"
    
    # Создаём postrm скрипт (выполняется после удаления)
    cat > "$DEB_DIR/DEBIAN/postrm" << 'EOF'
#!/bin/bash
set -e

X_USER=$(who | grep -E "\(:0\)" | awk '{print $1}' | head -n1)
if [ -z "$X_USER" ]; then
    X_USER=$(logname 2>/dev/null || echo "$SUDO_USER")
fi

if [ "$1" = "purge" ]; then
    # Удаляем конфигурацию пользователя
    if [ -n "$X_USER" ]; then
        USER_HOME=$(eval echo ~$X_USER)
        rm -f "$USER_HOME/.config/lswitch/user_dict.json"
        rm -f "$USER_HOME/.config/systemd/user/lswitch.service"
        rmdir "$USER_HOME/.config/lswitch" 2>/dev/null || true
    fi
    
    # Удаляем системную конфигурацию
    rm -rf /etc/lswitch
fi

echo "✓ LSwitch удалён"

exit 0
EOF
    
    chmod 755 "$DEB_DIR/DEBIAN/postrm"
    
    # Собираем пакет
    dpkg-deb --build "$DEB_DIR" "$BUILD_DIR/${PACKAGE_NAME}_${VERSION}_all.deb"
    rm -rf "$DEB_DIR"
    
    echo -e "${GREEN}✓ DEB пакет создан: $BUILD_DIR/${PACKAGE_NAME}_${VERSION}_all.deb${NC}"
}

# Функция сборки RPM пакета
build_rpm() {
    echo -e "${GREEN}📦 Сборка RPM пакета...${NC}"
    
    # Проверяем наличие rpmbuild
    if ! command -v rpmbuild &> /dev/null; then
        echo -e "${YELLOW}⚠️  rpmbuild не найден. Установите: sudo apt-get install rpm${NC}"
        return 1
    fi
    
    RPM_DIR="$BUILD_DIR/rpmbuild"
    mkdir -p "$RPM_DIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    
    # Создаём tarball с исходниками
    TARBALL="${PACKAGE_NAME}-${VERSION}.tar.gz"
    tar czf "$RPM_DIR/SOURCES/$TARBALL" \
        --transform "s,^,${PACKAGE_NAME}-${VERSION}/," \
        lswitch.py lswitch_control.py config/ \
        adapters/ utils/ 2>/dev/null || true
    
    # Создаём spec файл
    cat > "$RPM_DIR/SPECS/${PACKAGE_NAME}.spec" << EOF
Name:           $PACKAGE_NAME
Version:        $VERSION
Release:        1%{?dist}
Summary:        Automatic keyboard layout switcher for Linux

License:        MIT
URL:            https://github.com/yourusername/lswitch
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
Requires:       python3 >= 3.8, python3-evdev, python3-qt5, xclip, xdotool

%description
LSwitch automatically switches keyboard layouts based on typed text.
Features double Shift conversion, auto-conversion, self-learning dictionary,
and GUI control panel for KDE and Cinnamon.

%prep
%setup -q

%install
rm -rf %{buildroot}

# Создаём структуру каталогов
mkdir -p %{buildroot}/usr/local/bin
mkdir -p %{buildroot}/usr/local/lib/lswitch/{adapters,utils}
mkdir -p %{buildroot}/etc/lswitch
mkdir -p %{buildroot}/etc/udev/rules.d
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/scalable/apps

# Устанавливаем файлы
install -m 755 lswitch.py %{buildroot}/usr/local/bin/lswitch
install -m 755 lswitch_control.py %{buildroot}/usr/local/bin/lswitch-control
install -m 644 config/config.json.example %{buildroot}/etc/lswitch/config.json
install -m 644 config/lswitch-control.desktop %{buildroot}/usr/share/applications/
install -m 644 config/99-lswitch.rules %{buildroot}/etc/udev/rules.d/
install -m 644 assets/lswitch.svg %{buildroot}/usr/share/icons/hicolor/scalable/apps/

cp -r adapters/*.py %{buildroot}/usr/local/lib/lswitch/adapters/
cp -r utils/*.py %{buildroot}/usr/local/lib/lswitch/utils/

%files
/usr/local/bin/lswitch
/usr/local/bin/lswitch-control
/usr/local/lib/lswitch/
%config(noreplace) /etc/lswitch/config.json
/etc/udev/rules.d/99-lswitch.rules
/usr/share/applications/lswitch-control.desktop
/usr/share/icons/hicolor/scalable/apps/lswitch.svg

%post
# Добавляем пользователя в группу input
X_USER=\$(who | grep -E "\(:0\)" | awk '{print \$1}' | head -n1)
if [ -n "\$X_USER" ]; then
    usermod -a -G input "\$X_USER" 2>/dev/null || true
fi

%changelog
* $(date "+%a %b %d %Y") $MAINTAINER - $VERSION-1
- Initial RPM release

EOF
    
    # Собираем RPM
    rpmbuild --define "_topdir $RPM_DIR" -ba "$RPM_DIR/SPECS/${PACKAGE_NAME}.spec"
    
    # Копируем собранный пакет
    find "$RPM_DIR/RPMS" -name "*.rpm" -exec cp {} "$BUILD_DIR/" \;
    
    echo -e "${GREEN}✓ RPM пакет создан в $BUILD_DIR/${NC}"
}

# Функция создания архива для ручной установки
build_tarball() {
    echo -e "${GREEN}📦 Создание архива для ручной установки...${NC}"
    
    TARBALL="${PACKAGE_NAME}-${VERSION}.tar.gz"
    
    tar czf "$BUILD_DIR/$TARBALL" \
        --transform "s,^,${PACKAGE_NAME}-${VERSION}/," \
        lswitch.py lswitch_control.py config/ \
        install.sh README.md LICENSE requirements.txt \
        adapters/ utils/
    
    echo -e "${GREEN}✓ Архив создан: $BUILD_DIR/$TARBALL${NC}"
}

# Главное меню
echo "Выберите тип пакета для сборки:"
echo "  1) DEB (Debian/Ubuntu/Mint)"
echo "  2) RPM (Fedora/RHEL/openSUSE)"
echo "  3) TAR.GZ (универсальный архив)"
echo "  4) Все"
echo
read -p "Ваш выбор [1-4]: " choice

case $choice in
    1)
        build_deb
        ;;
    2)
        build_rpm
        ;;
    3)
        build_tarball
        ;;
    4)
        build_deb
        build_rpm
        build_tarball
        ;;
    *)
        echo -e "${RED}Неверный выбор${NC}"
        exit 1
        ;;
esac

echo
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✓ Сборка завершена!                  ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo
echo "Пакеты находятся в директории: $BUILD_DIR/"
ls -lh "$BUILD_DIR/"
