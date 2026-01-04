# LSwitch - Layout Switcher для Linux

Аналог Caramba Switcher для Linux - быстрый переключатель раскладки клавиатуры.

## Возможности

- ✅ **Конвертация по двойному Shift** - нажмите Shift дважды быстро
- ✅ Автоматическое переключение раскладки после конвертации
- ✅ Конвертация только последнего набранного слова
- ✅ Работает на уровне ядра (evdev) - **максимальная скорость**
- ✅ Работает везде: X11, Wayland, даже в консоли (tty)
- ✅ Поддержка EN ⟷ RU раскладок
- ✅ **Автозапуск через systemd демон**

## Быстрая установка

```bash
# Клонируйте репозиторий
git clone https://github.com/yourusername/lswitch.git
cd lswitch

# Установите в систему (потребуются права root)
sudo ./install.sh
```

Скрипт установки автоматически:
- Установит необходимые зависимости (python3-evdev)
- Скопирует файлы в систему
- Настроит systemd демон
- Предложит включить автозапуск

## Управление сервисом

После установки используйте стандартные команды systemd:

```bash
# Запустить
sudo systemctl start lswitch

# Остановить
sudo systemctl stop lswitch

# Перезапустить
sudo systemctl restart lswitch

# Статус
sudo systemctl status lswitch

# Включить автозапуск
sudo systemctl enable lswitch

# Отключить автозапуск
sudo systemctl disable lswitch

# Просмотр логов в реальном времени
sudo journalctl -u lswitch -f
```

### Или используйте Makefile

```bash
make install    # Установить
make start      # Запустить
make stop       # Остановить
make restart    # Перезапустить
make status     # Статус
make enable     # Включить автозапуск
make logs       # Просмотр логов
make uninstall  # Удалить из системы
```

## Ручной запуск (без установки)

### Системные зависимости

```bash
sudo apt install python3-evdev
```

### Запуск

⚠️ **Требуются права root** для доступа к `/dev/input/`:

```bash
sudo python3 lswitch.py
```

## Использование

1. Запустите программу
2. Печатайте текст в любом приложении
3. Набрали слово не в той раскладке? Нажмите **Shift дважды** быстро
4. Последнее слово автоматически конвертируется и раскладка переключается! ✨

### Примеры

- `ghbdtn` → `привет` (при двойном Shift + автопереключение раскладки)
- `руддщ цщкдв` → `hello world` (при двойном Shift + автопереключение раскладки)

## Конфигурация

Файл конфигурации после установки находится в `/etc/lswitch/config.json`:

```json
{
  "double_click_timeout": 0.3,
  "debug": false,
  "switch_layout_after_convert": true,
  "layout_switch_key": "Alt_L+Shift_L"
}
```

### Параметры

- `double_click_timeout` - максимальное время между нажатиями Shift (в секундах)
- `debug` - включить отладочные сообщения
- `switch_layout_after_convert` - автоматически переключать раскладку после конвертации
- `layout_switch_key` - комбинация клавиш для переключения раскладки

После изменения конфигурации перезапустите сервис:
```bash
sudo systemctl restart lswitch
```

## Удаление

```bash
sudo ./uninstall.sh
# Или
make uninstall
```
{ от root: `sudo python3 lswitch.py`
2. Печатайте текст в любом приложении
3. Набрали слово не в той раскладке? Нажмите **Shift дважды** быстро
4. Последнее слово автоматически конвертируется и раскладка переключается! ✨

### Примеры

- `ghbdtn` → двойной Shift → `привет` (автопереключение на RU)
- `руддщ` → двойной Shift → `hello` (автопереключение на EN)
- `ntcn cdjql` → пробел разделяет слова → двойной Shift конвертирует только `cdjql` → `свой`

- **double_click_timeout** (0.3) - время между нажатиями Shift в секундах
- **debug** (true/false) - показывать отладочные сообщения
- **switch_layout_after_convert** (true/false) - переключать раскладку после конвертации
- **layout_switch_key** - шорткат переключения раскладки:
  - `Alt_L+Shift_L` (по умолчанию, Alt+Shift)
  - `Ctrl_L+Shift_L` (Ctrl+Shift)
  - `Super_L+space` (Win+Space)
  - Или ваш собственный шорткат

## Выход

Нажмите **ESC** для выхода из программы.
 через systemd

Создайте файл `/etc/systemd/system/lswitch.service`:

```ini
[Unit]
Description=LSwitch Keyboard Layout Switcher
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /полный/путь/к/lswitch.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Активируйте сервис:

```bash
sudo systemctl enable --now lswitch
sudo systemctl status lswitch
```

## Требования

- Linux (любой дистрибутив с evdev)
- Python 3.6+
- python3-evdev
- Права root

## Технические детали

- Работает на уровне `/dev/input/` через evdev
- Создаёт виртуальную клавиатуру для эмуляции событий
- Фильтрует собственные события по имени устройства (нет зацикливания)
- Буфер сбрасывается при пробеле/Enter (конвертирует только последнее слово)ol
- xclip

## Лицензия

MIT
