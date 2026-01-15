# ✅ Чеклист перед установкой

## Предварительная проверка

- [ ] У вас есть права sudo/root
- [ ] Система на базе Linux (Debian/Ubuntu или совместимая)
- [ ] Установлен Python 3.6 или новее (`python3 --version`)
- [ ] Установлен systemd (`systemctl --version`)

## Проверка файлов проекта

```bash
# Убедитесь, что все файлы на месте
ls -l install.sh uninstall.sh lswitch.service Makefile lswitch.py

# Проверьте права на выполнение
ls -l *.sh
# Должны быть: -rwxr-xr-x
```

## Установка

### Шаг 1: Запуск установки

```bash
sudo ./install.sh
```

### Шаг 2: Выбор автозапуска

Когда появится вопрос:
```
Включить автозапуск при загрузке системы? (y/n):
```

- Нажмите `y` - для включения автозапуска (рекомендуется)
- Нажмите `n` - для ручного управления

### Шаг 3: Проверка установки

```bash
# Проверить статус
sudo systemctl status lswitch

# Должно быть: Active: active (running)
```

## После установки

- [ ] Сервис запущен: `sudo systemctl status lswitch`
- [ ] Автозапуск включён: `systemctl is-enabled lswitch` (должно быть: enabled)
- [ ] Конфигурация создана: `ls -l /etc/lswitch/config.json`
- [ ] Команда `lswitch` доступна в PATH: `command -v lswitch` (или используйте `python3 -m lswitch`)

## Тестирование

- [ ] Откройте любой текстовый редактор
- [ ] Наберите: `ghbdtn`
- [ ] Быстро нажмите Shift дважды
- [ ] Результат: `привет` ✨
- [ ] Раскладка переключилась автоматически

## Просмотр логов

```bash
# Логи в реальном времени
sudo journalctl -u lswitch -f

# Последние 50 записей
sudo journalctl -u lswitch -n 50
```

## Если что-то пошло не так

### Сервис не запускается

```bash
# Смотрим логи с ошибками
sudo journalctl -u lswitch -n 100

# Пробуем запустить вручную для диагностики
sudo python3 -u -m lswitch
```

### Не работает конвертация

1. Убедитесь, что сервис запущен:
   ```bash
   sudo systemctl status lswitch
   ```

2. Проверьте права доступа к /dev/input/:
   ```bash
   ls -l /dev/input/
   ```

3. Увеличьте timeout в конфигурации:
   ```bash
   sudo nano /etc/lswitch/config.json
   # Измените "double_click_timeout": 0.3 на 0.5
   sudo systemctl restart lswitch
   ```

### Конфликт с другими программами

Если у вас установлены другие программы для раскладки:
- xneur
- kbdd
- другие подобные утилиты

Попробуйте остановить их или настроить другие горячие клавиши.

## Удаление (если нужно)

```bash
sudo ./uninstall.sh
```

## Дополнительная помощь

- README.md - Общая информация
- INSTALL.md - Детальное руководство
- EXAMPLES.md - Примеры использования
- DEPLOYMENT.md - Полная документация

---

**Готово? Запустите: `sudo ./install.sh`** 🚀
