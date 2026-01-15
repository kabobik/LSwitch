# Руководство по установке и настройке LSwitch

## 🚀 Быстрая установка

### 1. Установка в систему

```bash
# Из директории проекта
sudo ./install.sh
```

Скрипт автоматически:
- Установит python3-evdev
- Установит пакет (через pip) и создаст консольный скрипт `lswitch` (альтернативно `python3 -m lswitch`)
- Создаст конфигурацию в /etc/lswitch/
- Установит systemd сервис
- Предложит включить автозапуск

### 2. Включение автозапуска

```bash
sudo systemctl enable lswitch
sudo systemctl start lswitch
```

Или просто выберите "y" при установке.

## 📋 Структура установки

После установки файлы будут размещены:

```
/usr/local/bin/lswitch              - исполняемый файл
/etc/lswitch/config.json            - конфигурация
/etc/systemd/system/lswitch.service - systemd unit
```

## 🎛️ Управление сервисом

### Через systemctl:

```bash
sudo systemctl start lswitch       # Запустить
sudo systemctl stop lswitch        # Остановить
sudo systemctl restart lswitch     # Перезапустить
sudo systemctl status lswitch      # Статус
sudo systemctl enable lswitch      # Включить автозапуск
sudo systemctl disable lswitch     # Отключить автозапуск
```

### Через Makefile (из директории проекта):

```bash
make start       # Запустить
make stop        # Остановить
make restart     # Перезапустить
make status      # Статус
make enable      # Включить автозапуск
make disable     # Отключить автозапуск
make logs        # Логи в реальном времени
```

## 📝 Логи

Просмотр логов:

```bash
# В реальном времени
sudo journalctl -u lswitch -f

# Последние 100 строк
sudo journalctl -u lswitch -n 100

# С определённого времени
sudo journalctl -u lswitch --since "1 hour ago"
```

## ⚙️ Настройка

Файл конфигурации: `/etc/lswitch/config.json`

```json
{
  "double_click_timeout": 0.3,
  "debug": false,
  "switch_layout_after_convert": true,
  "layout_switch_key": "Alt_L+Shift_L"
}
```

После изменения конфигурации:

```bash
sudo systemctl restart lswitch
```

## 🧪 Тестирование

Проверьте, что сервис работает:

```bash
# Статус
sudo systemctl status lswitch

# Должен показать: Active: active (running)
```

Попробуйте в любом текстовом редакторе:
1. Введите: `ghbdtn`
2. Быстро нажмите Shift дважды
3. Должно получиться: `привет` (и раскладка переключится)

## 🗑️ Удаление

```bash
sudo ./uninstall.sh
# Или
make uninstall
```

## ❓ Устранение проблем

### Сервис не запускается

```bash
# Проверьте логи
sudo journalctl -u lswitch -n 50

# Проверьте установку и права на команду `lswitch`
command -v lswitch || echo "lswitch не найден; попробуйте: python3 -m lswitch"

# Попробуйте запустить вручную
sudo python3 -m lswitch
```

### Не работает конвертация

1. Проверьте, что сервис запущен:
   ```bash
   sudo systemctl status lswitch
   ```

2. Проверьте логи на ошибки:
   ```bash
   sudo journalctl -u lswitch -f
   ```

3. Попробуйте увеличить `double_click_timeout` в конфигурации

### Конфликты с другими программами

Если у вас установлены другие программы для работы с раскладкой клавиатуры, они могут конфликтовать. Остановите их или настройте другие горячие клавиши.

## 🔧 Разработка

Для тестирования без установки:

```bash
# Запуск из исходников
sudo python3 lswitch.py

# Запуск тестов
python3 -m pytest test_lswitch.py
```

## 📦 Сборка пакета

Для создания deb-пакета (будущее):

```bash
# TODO: добавить создание deb-пакета
```
