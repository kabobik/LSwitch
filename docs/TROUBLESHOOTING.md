# Устранение проблем LSwitch

## Быстрая диагностика

```bash
# Статус демона
systemctl --user status lswitch

# Логи
journalctl --user-unit=lswitch -n 30

# Или через make
make status
make logs
```

## Типичные проблемы

### 1. Демон не запускается

```bash
systemctl --user status lswitch
```

Если `inactive` — запустите:
```bash
systemctl --user enable --now lswitch
```

### 2. Нет прав доступа к /dev/input/

**Симптомы:**
```
PermissionError: [Errno 13] Permission denied: '/dev/input/event0'
```

**Решение:**
```bash
# Добавить пользователя в группу input
sudo usermod -a -G input $USER
# Перелогиниться для применения
```

### 3. Нет python3-evdev

```
ModuleNotFoundError: No module named 'evdev'
```

**Решение:**
```bash
sudo apt install python3-evdev
# Или переустановить
bash scripts/install.sh
```

### 4. Двойная конвертация (текст моргает)

Сервис не имеет доступа к X11. Проверьте:
```bash
systemctl --user show lswitch | grep Environment
```

Должны быть `DISPLAY` и `XAUTHORITY`. При установке через `scripts/install.sh` настраивается автоматически.

### 5. Конфликт с другими программами

Если установлены xneur, kbdd или аналоги — отключите их:
```bash
sudo systemctl stop xneur && sudo systemctl disable xneur
```

### 6. Виртуальная клавиатура зависла

Если после аварийного завершения `/dev/uinput` занят:
```bash
python3 scripts/release_virtual_kb.py --kill
```

## Полная переустановка

```bash
bash scripts/uninstall.sh
bash scripts/install.sh
```

## Проверка работы

1. Откройте текстовый редактор
2. Наберите: `ghbdtn`
3. Быстро нажмите Shift дважды
4. Должно получиться: `привет`

## Полезные ссылки

- [INSTALL.md](INSTALL.md) — установка
- [QUICKSTART.md](QUICKSTART.md) — быстрый старт
