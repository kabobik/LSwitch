# 🔧 Устранение проблем LSwitch

## Проблема: Сервис не работает после установки

### Решение

Проблема была в буферизации вывода Python при работе через systemd. Исправлено в последней версии.

### Быстрая диагностика

```bash
# Запустите диагностику
sudo ./diagnose.sh
# Или
make diagnose
```

### Шаги устранения

1. **Остановите старый сервис:**
   ```bash
   sudo systemctl stop lswitch
   ```

2. **Обновите файлы:**
   ```bash
   sudo cp lswitch.service /etc/systemd/system/
   sudo cp lswitch.py /usr/local/bin/lswitch
   sudo chmod +x /usr/local/bin/lswitch
   ```

3. **Перезагрузите systemd:**
   ```bash
   sudo systemctl daemon-reload
   ```

4. **Запустите сервис:**
   ```bash
   sudo systemctl start lswitch
   ```

5. **Проверьте логи:**
   ```bash
   sudo journalctl -u lswitch -n 20
   ```

   Должны увидеть:
   ```
   🚀 LSwitch запущен
   ✓ Конфиг загружен: /etc/lswitch/config.json
   🚀 LSwitch запущен (evdev режим)!
   ✓ Мониторинг XX устройств
   ```

### Что было исправлено

1. **systemd service файл** ([lswitch.service](lswitch.service)):
   - Добавлен флаг `-u` для Python (unbuffered)
   - Добавлена переменная окружения `PYTHONUNBUFFERED=1`
   - Добавлена рабочая директория `WorkingDirectory=/etc/lswitch`
   - **Добавлены переменные X11**: `DISPLAY=:0` и `XAUTHORITY=/home/user/.Xauthority`

2. **Python скрипт** ([lswitch.py](lswitch.py)):
   - Добавлена принудительная отключение буферизации stdout/stderr
   - Добавлены `flush=True` для всех print()
   - Улучшенная обработка ошибок с traceback

3. **Установочный скрипт** ([install.sh](install.sh)):
   - Автоматическое определение пользователя X-сессии
   - Подстановка правильного XAUTHORITY в unit файл

## Типичные проблемы

### 1. Логи пустые

**Симптомы:**
```bash
sudo journalctl -u lswitch
# Показывает только "Started lswitch.service..."
```

**Решение:**
Обновите сервис (см. "Шаги устранения" выше)

### 2. Сервис не запускается

**Проверка:**
```bash
sudo systemctl status lswitch
```

**Если показывает "failed":**
```bash
# Смотрим подробные логи
sudo journalctl -u lswitch -n 50

# Пробуем запустить вручную
sudo python3 -u -m lswitch
```

### 3. Нет python3-evdev

**Симптомы:**
```
ModuleNotFoundError: No module named 'evdev'
```

**Решение:**
```bash
sudo apt update
sudo apt install python3-evdev
sudo systemctl restart lswitch
```

### 4. Нет прав доступа к /dev/input/

**Симптомы:**
```
PermissionError: [Errno 13] Permission denied: '/dev/input/event0'
```

**Решение:**
Сервис должен запускаться от root (это уже настроено в systemd)

### 5. Двойная конвертация (текст моргает)

**Симптомы:**
При двойном Shift текст конвертируется, но сразу возвращается обратно.

**Причина:**
Сервис запущен от root без доступа к X11 сессии пользователя.

**Решение:**
Проверьте переменные окружения сервиса:
```bash
sudo systemctl show lswitch | grep Environment=
```

Должно быть:
```
Environment=PYTHONUNBUFFERED=1 DISPLAY=:0 XAUTHORITY=/home/USERNAME/.Xauthority
```

Если их нет - переустановите сервис:
```bash
sudo ./uninstall.sh
sudo ./install.sh
```

### 6. Конфликт с другими программами

Если у вас установлены:
- xneur
- kbdd
- другие программы для раскладки

Они могут конфликтовать. Попробуйте остановить их:
```bash
sudo systemctl stop xneur
sudo systemctl disable xneur
```

## Полная переустановка

Если ничего не помогает:

```bash
# 1. Удалите старую версию
sudo ./uninstall.sh

# 2. Установите заново
sudo ./install.sh

# 3. Включите автозапуск
sudo systemctl enable lswitch
sudo systemctl start lswitch

# 4. Проверьте
sudo systemctl status lswitch
sudo journalctl -u lswitch -f
```

## Полезные команды

```bash
# Статус
sudo systemctl status lswitch

# Логи в реальном времени
sudo journalctl -u lswitch -f

# Последние 50 записей
sudo journalctl -u lswitch -n 50

# Логи с ошибками
sudo journalctl -u lswitch -p err

# Перезапуск
sudo systemctl restart lswitch

# Диагностика
sudo ./diagnose.sh
make diagnose

# Ручной запуск (для теста)
sudo /usr/bin/python3 -u /usr/local/bin/lswitch
```

## Проверка работы

1. Откройте текстовый редактор
2. Наберите: `ghbdtn`
3. Быстро нажмите Shift дважды
4. Должно получиться: `привет`
5. Раскладка переключится автоматически

Если работает — всё в порядке! ✅

## Дополнительная помощь

- [INSTALL.md](INSTALL.md) - Детальное руководство
- [EXAMPLES.md](EXAMPLES.md) - Примеры использования
- [diagnose.sh](diagnose.sh) - Скрипт диагностики
