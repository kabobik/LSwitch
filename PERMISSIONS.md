# LSwitch - Права доступа к устройствам ввода

## Проблема

LSwitch использует библиотеку `evdev` для перехвата событий клавиатуры на уровне ядра Linux.  
Это требует доступа к `/dev/input/eventX` устройствам, которые по умолчанию доступны только root.

## Решение через udev + группа input

### ✅ Рекомендуемый способ (безопасно)

Скрипт `install.sh` автоматически:

1. **Создает udev правило** `/etc/udev/rules.d/99-lswitch.rules`:
   ```
   KERNEL=="event*", SUBSYSTEM=="input", MODE="0660", GROUP="input"
   ```

2. **Создает группу `input`** (если не существует)

3. **Добавляет вашего пользователя в группу `input`**:
   ```bash
   sudo usermod -a -G input $USER
   ```

4. **⚠️ ВАЖНО: Требуется перелогиниться!**
   - Выйдите из системы и войдите снова
   - Или перезагрузитесь: `sudo reboot`

### Проверка прав

После перелогина проверьте:

```bash
# Проверить что вы в группе input
groups $USER
# Должно быть: anton adm cdrom sudo dip plugdev input ...

# Проверить права на устройства
ls -l /dev/input/event*
# Должно быть: crw-rw---- 1 root input ... /dev/input/eventX

# Проверить что можете читать события
sudo chmod 660 /dev/input/event* && \
python3 -c "import evdev; print('OK')"
```

## Альтернативные способы (не рекомендуется)

### 1. Запуск от root через systemd

```bash
sudo systemctl start lswitch
sudo systemctl enable lswitch
```

**Минусы:**
- Требует systemd
- Работает только в режиме демона
- GUI версия не может использовать этот способ

### 2. sudo NOPASSWD (небезопасно!)

```bash
# НЕ ДЕЛАЙТЕ ТАК! Небезопасно!
echo "$USER ALL=(ALL) NOPASSWD: /usr/local/bin/lswitch" | sudo tee /etc/sudoers.d/lswitch
```

**Минусы:**
- Дыра в безопасности
- Требует sudo каждый раз

### 3. setcap capabilities

```bash
sudo setcap cap_dac_read_search=ep /usr/local/bin/lswitch
```

**Минусы:**
- Не работает с скриптами Python
- Требует компилированный бинарник

## Почему udev + группа input?

✅ **Безопасно** - пользователь получает доступ только к input устройствам  
✅ **Стандартно** - используется многими дистрибутивами (Ubuntu, Debian, Arch)  
✅ **Постоянно** - права сохраняются после перезагрузки  
✅ **Удобно** - работает для GUI и демона  

## Устранение проблем

### Ошибка: Permission denied /dev/input/eventX

```bash
# 1. Проверьте что правило установлено
ls -l /etc/udev/rules.d/99-lswitch.rules

# 2. Перезагрузите udev
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3. Проверьте группу input
getent group input

# 4. Проверьте что вы в группе
groups $USER | grep input

# 5. Если нет - добавьте вручную
sudo usermod -a -G input $USER

# 6. ПЕРЕЛОГИНЬТЕСЬ!
# Группы применяются только после перелогина
```

### GUI версия не работает после установки

```bash
# Проверьте что перелогинились
groups
# Должна быть группа input

# Если нет - перелогиньтесь или перезагрузитесь
sudo reboot
```

### Работает только с sudo

Это значит вы забыли перелогиниться после установки!

```bash
# Проверка
id -nG | grep input

# Если пусто - перелогиньтесь
pkill -KILL -u $USER  # Осторожно! Закроет все ваши программы
```

## Проверка после установки

```bash
# 1. Группа input существует
getent group input

# 2. Вы в группе input
id -nG | grep input

# 3. udev правило установлено
cat /etc/udev/rules.d/99-lswitch.rules

# 4. Устройства принадлежат группе input
ls -l /dev/input/event* | head -3

# 5. Можете читать без sudo
python3 << EOF
import evdev
devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
print(f"Найдено {len(devices)} устройств")
for dev in devices:
    print(f"  - {dev.name}")
EOF
```

Если последняя команда работает без sudo - всё настроено правильно! ✅

## Удаление

Если хотите убрать права доступа:

```bash
# Удалить udev правило
sudo rm /etc/udev/rules.d/99-lswitch.rules
sudo udevadm control --reload-rules

# Удалить из группы
sudo gpasswd -d $USER input

# Перелогиниться
```
