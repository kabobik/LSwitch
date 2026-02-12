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

**Причина:** Пользователь не в группе `input`

**Проверка:**
```bash
# Проверить группы пользователя
groups | grep input

# Если output пустой - вас нет в группе input
```

**Решение:**

1. Добавить пользователя в группу input:
```bash
sudo usermod -a -G input $USER
```

2. **Обязательно перелогиниться!** (выйти и войти заново)
   - Изменения групп применяются только после перелогина
   - `su - $USER` не поможет — нужен полный logout

3. Проверить снова:
```bash
groups | grep input
# Должно показать "input" в списке групп
```

4. Проверить доступ к устройствам:
```bash
ls -l /dev/input/event* | head -3
# Вывод должен содержать: crw-rw---- 1 root input
```

5. Запустить демон:
```bash
systemctl --user restart lswitch
```

**Если не помогло:**

- Проверьте udev правила:
```bash
cat /etc/udev/rules.d/99-lswitch.rules
# Должно быть: KERNEL=="event*", SUBSYSTEM=="input", MODE="0660", GROUP="input"
```

- Перезагрузите udev:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
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
