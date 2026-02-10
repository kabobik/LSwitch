# Установка LSwitch

## Быстрая установка

```bash
git clone https://github.com/kirill-2l/LSwitch.git
cd LSwitch
bash scripts/install.sh
```

Скрипт автоматически:
- Установит системные зависимости (`xclip`, `xdotool`)
- Установит пакет через `pip install -e .`
- Скопирует systemd unit, udev-правила, .desktop файл
- Добавит пользователя в группу `input`
- Предложит включить автозапуск

## Ручная установка

```bash
# Зависимости
sudo apt install python3-dev xclip xdotool

# Установка пакета
sudo pip3 install --break-system-packages -e .

# Права доступа к клавиатуре
sudo usermod -a -G input $USER
# Перелогиниться!

# Запуск
systemctl --user enable --now lswitch
```

## Управление сервисом

```bash
systemctl --user start lswitch      # Запустить
systemctl --user stop lswitch       # Остановить
systemctl --user restart lswitch    # Перезапустить
systemctl --user status lswitch     # Статус
systemctl --user enable lswitch     # Автозапуск ON
systemctl --user disable lswitch    # Автозапуск OFF
```

Или через Makefile:

```bash
make start / stop / restart / status / enable / disable / logs
```

## Логи

```bash
journalctl --user-unit=lswitch -f          # В реальном времени
journalctl --user-unit=lswitch -n 100      # Последние 100 строк
# Или
make logs
```

## Настройка

Конфигурация: `~/.config/lswitch/config.json` (создаётся автоматически).

Основные параметры:

```json
{
  "double_click_timeout": 0.3,
  "debug": false,
  "switch_layout_after_convert": true,
  "auto_switch": false,
  "auto_switch_threshold": 10
}
```

Изменения вступают в силу после `systemctl --user restart lswitch`.

Также можно менять настройки через GUI: `lswitch-control`.

## Проверка

1. Откройте текстовый редактор
2. Наберите: `ghbdtn`
3. Быстро нажмите Shift дважды
4. Должно получиться: `привет`

## Удаление

```bash
bash scripts/uninstall.sh
# Или
make uninstall
```

## Разработка

```bash
# Запуск из исходников
lswitch --debug

# Тесты
python3 -m pytest tests/ -v
# Или
make test
```

## См. также

- [QUICKSTART.md](QUICKSTART.md) — краткий старт
- [PERMISSIONS.md](PERMISSIONS.md) — права доступа
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — устранение проблем
