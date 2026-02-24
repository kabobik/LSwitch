# Примеры команд и вывода

## Установка

```bash
$ sudo ./install.sh

╔════════════════════════════════════════╗
║   LSwitch - Установка в систему        ║
╚════════════════════════════════════════╝

📦 Установка зависимостей...
python3-evdev уже установлен

📁 Копирование файлов...
/usr/local/bin/lswitch установлен
/etc/lswitch/config.json создан

⚙️  Установка systemd сервиса...
Демон перезагружен

✅ Установка завершена!

Управление сервисом:
  • Запустить:           sudo systemctl start lswitch
  • Остановить:          sudo systemctl stop lswitch
  • Перезапустить:       sudo systemctl restart lswitch
  • Статус:              sudo systemctl status lswitch
  • Включить автозапуск: sudo systemctl enable lswitch
  • Отключить автозапуск: sudo systemctl disable lswitch

Логи:
  sudo journalctl -u lswitch -f

Конфигурация:
  /etc/lswitch/config.json

Включить автозапуск при загрузке системы? (y/n): y
Created symlink /etc/systemd/system/multi-user.target.wants/lswitch.service → /etc/systemd/system/lswitch.service.
✅ Автозапуск включён и сервис запущен!
```

## Проверка статуса

```bash
$ sudo systemctl status lswitch

● lswitch.service - LSwitch - Layout Switcher (evdev)
     Loaded: loaded (/etc/systemd/system/lswitch.service; enabled; vendor preset: enabled)
     Active: active (running) since Sun 2026-01-05 01:20:00 MSK; 5min ago
       Docs: https://github.com/kabobik/lswitch
   Main PID: 12345 (python3)
      Tasks: 1 (limit: 4915)
     Memory: 15.2M
        CPU: 245ms
     CGroup: /system.slice/lswitch.service
             └─12345 /usr/bin/python3 /usr/local/bin/lswitch

янв 05 01:20:00 hostname systemd[1]: Started LSwitch - Layout Switcher (evdev).
янв 05 01:20:00 hostname lswitch[12345]: 🚀 LSwitch запущен
янв 05 01:20:00 hostname lswitch[12345]:    Двойное нажатие Shift = конвертация последнего слова
```

## Просмотр логов

```bash
$ sudo journalctl -u lswitch -f

-- Journal begins at Mon 2026-01-01 00:00:00 MSK. --
янв 05 01:20:00 hostname systemd[1]: Started LSwitch - Layout Switcher (evdev).
янв 05 01:20:00 hostname lswitch[12345]: 🚀 LSwitch запущен
янв 05 01:20:00 hostname lswitch[12345]:    Двойное нажатие Shift = конвертация последнего слова
янв 05 01:20:00 hostname lswitch[12345]:    Ctrl+C = выход
янв 05 01:20:00 hostname lswitch[12345]: ✓ Конфиг загружен: /etc/lswitch/config.json
янв 05 01:20:00 hostname lswitch[12345]: ✓ Найдено устройств ввода: 3
янв 05 01:20:15 hostname lswitch[12345]: 🔄 Конвертация: 'ghbdtn' → 'привет'
янв 05 01:20:15 hostname lswitch[12345]: ✓ Раскладка переключена
```

## Управление через Makefile

```bash
$ make status
sudo systemctl status lswitch --no-pager
● lswitch.service - LSwitch - Layout Switcher (evdev)
     Loaded: loaded (/etc/systemd/system/lswitch.service; enabled)
     Active: active (running) since Sun 2026-01-05 01:20:00 MSK; 10min ago

$ make restart
🔄 Перезапуск LSwitch...
● lswitch.service - LSwitch - Layout Switcher (evdev)
     Loaded: loaded (/etc/systemd/system/lswitch.service; enabled)
     Active: active (running) since Sun 2026-01-05 01:30:00 MSK; 1s ago

$ make logs
sudo journalctl -u lswitch -f
-- Logs begin at Mon 2026-01-01 00:00:00 MSK. --
янв 05 01:30:00 hostname lswitch[12346]: 🚀 LSwitch запущен
янв 05 01:30:00 hostname lswitch[12346]: ✓ Конфиг загружен: /etc/lswitch/config.json
```

## Удаление

```bash
$ sudo ./uninstall.sh

╔════════════════════════════════════════╗
║   LSwitch - Удаление из системы        ║
╚════════════════════════════════════════╝

Остановка сервиса...
Removed /etc/systemd/system/multi-user.target.wants/lswitch.service.

Удаление файлов...
Перезагрузка systemd...
✅ LSwitch успешно удалён из системы!
```

## Тестирование конвертации

Откройте любой текстовый редактор и попробуйте:

1. Наберите: `ghbdtn vbh`
2. Быстро нажмите Shift дважды
3. Результат: `привет мир`
4. Раскладка автоматически переключится на русскую

Или наоборот:

1. Наберите: `руддщ цщкдв`
2. Быстро нажмите Shift дважды
3. Результат: `hello world`
4. Раскладка автоматически переключится на английскую
