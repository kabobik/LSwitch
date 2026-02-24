# Конфигурационные файлы

## Файлы systemd и desktop
- `lswitch.service` - systemd сервис для демона
- `lswitch-control.desktop` - desktop entry для панели управления
- `lswitch-tray.desktop` - desktop entry для трея

## Конфигурация
- `config.json.example` - пример конфигурации
- `99-lswitch.rules` - udev правила для доступа к устройствам

## Использование
```bash
# Скопировать в системную директорию
sudo cp 99-lswitch.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules

# Установить systemd сервис
cp lswitch.service ~/.config/systemd/user/
systemctl --user enable lswitch
```
