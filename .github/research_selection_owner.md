# Исследование: Определение активного выделения в X11

**Дата:** 2026-02-20  
**Статус:** ✅ Решение найдено

---

## Проблема

X11 PRIMARY selection НИКОГДА не очищается — он всегда хранит последний выделенный текст. Даже когда пользователь кликнул в пустое поле и ничего не выделено, `xclip -selection primary -o` возвращает старый текст.

Предыдущие попытки не работают:
1. `if primary_after == primary_before` — ломает повторное выделение того же текста
2. `if primary_after == primary_before and not primary_after.strip()` — не работает т.к. PRIMARY никогда не пустой

---

## Решение: XGetSelectionOwner

### Ключевой инсайт

В X11 каждая selection (PRIMARY, CLIPBOARD, etc.) имеет **владельца** — окно которое владеет данными selection. Когда пользователь делает НОВОЕ выделение, **владелец меняется** на окно где сделано выделение.

### API

```python
from Xlib import X, display, Xatom

d = display.Display()
owner = d.get_selection_owner(Xatom.PRIMARY)
owner_id = owner.id if owner != X.NONE else 0
d.close()
```

### Тестовые результаты

| Сценарий | owner изменился | текст изменился | Результат |
|----------|-----------------|-----------------|-----------|
| ctrl+shift+Left в пустом поле | ❌ Нет | ❌ Нет | Нет выделения |
| Новое выделение (другой текст) | ✅ Да | ✅ Да | Есть выделение |
| Повторное выделение того же текста | ✅ Да | ❌ Нет | Есть выделение |
| xclip устанавливает selection | ✅ Да | ✅ Да | Есть владелец |

**Ключевой тест:** Даже при повторном выделении того же текста, owner меняется!

---

## Рекомендуемая реализация

### 1. Добавить в `lswitch/xkb.py`:

```python
def get_selection_owner_id() -> int:
    """Возвращает Window ID владельца PRIMARY selection, или 0 если нет владельца.
    
    Используется для определения было ли создано НОВОЕ выделение:
    - Если owner_id изменился после ctrl+shift+Left → выделение создано
    - Если owner_id не изменился → пустое поле или выделение не изменилось
    """
    try:
        from Xlib import X, display, Xatom
        d = display.Display()
        owner = d.get_selection_owner(Xatom.PRIMARY)
        owner_id = owner.id if owner != X.NONE else 0
        d.close()
        return owner_id
    except Exception:
        return 0
```

### 2. Изменить логику в `lswitch/core.py` (строки ~1207-1240):

**Было:**
```python
# Сохраняем PRIMARY ДО попытки выделения
primary_before = self.last_known_selection
...
# После ctrl+shift+Left
result = self.system.xclip_get(selection='primary', timeout=0.3)
primary_after = result.stdout if result else ""
# Пропускаем только если текст не изменился И пустой
if primary_after == primary_before and not primary_after.strip():
    # Выделение не произошло — пустое поле
```

**Надо:**
```python
from lswitch.xkb import get_selection_owner_id

# Сохраняем состояние ДО попытки выделения
owner_before = get_selection_owner_id()
primary_before = self.last_known_selection
...
# После ctrl+shift+Left
owner_after = get_selection_owner_id()
result = self.system.xclip_get(selection='primary', timeout=0.3)
primary_after = result.stdout if result else ""

# Новое выделение создано если:
# 1. owner изменился, ИЛИ
# 2. текст изменился
has_new_selection = (owner_after != owner_before) or (primary_after != primary_before)

if not has_new_selection:
    # owner и текст не изменились → НЕТ нового выделения (пустое поле)
    if self.config.get('debug'):
        print("⚠️ No new selection detected (owner and text unchanged) — skipping conversion")
    self.last_shift_press = 0
    return
```

---

## Edge Cases

### Clipboard Managers

Если clipboard manager (типа "Chromium clipboard") активен:
- Он может перехватить ownership ПОСЛЕ выделения
- **Но:** мы проверяем owner СРАЗУ после ctrl+shift+Left (через 30мс)
- На практике приложение успевает стать владельцем до перехвата

### Одно и то же окно

Если пользователь делает выделение в том же окне где был предыдущее:
- owner_id может остаться тем же
- **Но:** текст скорее всего изменится
- Комбинированная проверка `owner OR text` покрывает этот случай

---

## Тестовый скрипт

Для проверки работоспособности:

```bash
python3 << 'EOF'
from Xlib import X, display, Xatom
import subprocess

def get_owner_id():
    d = display.Display()
    owner = d.get_selection_owner(Xatom.PRIMARY)
    result = owner.id if owner != X.NONE else 0
    d.close()
    return result

def get_primary():
    result = subprocess.run(['xclip', '-selection', 'primary', '-o'], 
                          capture_output=True, text=True)
    return result.stdout

print(f"Owner ID: {get_owner_id()}")
print(f"PRIMARY: {repr(get_primary()[:50])}")
EOF
```

---

## Вывод

✅ **XGetSelectionOwner решает проблему** определения активного выделения:

1. Работает для повторного выделения того же текста
2. Работает для определения "пустого поля"
3. Не требует таймеров или сложной логики
4. Использует стандартный X11 API через python-xlib (уже в зависимостях)

**Интеграция:** ~15 строк кода в `xkb.py` + ~10 строк изменений в `core.py`
