# Wayland-портация LSwitch: KDE-first, Qt6-native

> **Статус документа:** это исследовательские заметки, а не актуальный план реализации. Здесь сохранены гипотезы, промежуточные решения и утверждения, которые могли оказаться неточными после сверки с кодом.
>
> **Актуальный рабочий план:** `docs/WAYLAND_IMPLEMENTATION_PLAN.md`.
>
> **Особенно осторожно:** утверждения про `QClipboard.Selection`, `selectionChanged()` и headless-режим через Qt требуют feature detection и fallback-стратегий. На Wayland нельзя считать X11 PRIMARY semantics доступными по умолчанию.

> **Подход:** Полный переход на **PyQt6** (Qt 6) без compatibility-слоёв. Qt 6 трактует Wayland как первоклассную платформу и даёт рабочий `QtDBus`, стабильный `QClipboard` и `selectionChanged` на Wayland. `send_combo()` через UInput заменяет `xdotool`. Subprocess (`wl-clipboard`) — только fallback для headless-режима.
>
> **Почему PyQt6, а не PyQt5:**
> - `QtDBus` в PyQt5 на Linux содержит баги — `QDBusInterface.call()` возвращает невалидные `QDBusMessage`. В PyQt6 исправлено.
> - Qt 5 — X11-first, Wayland вторичен. Qt 6 — Wayland-first, `QClipboard` и `wp_primary_selection` стабильнее.
> - Qt 5 / PyQt5 — end-of-life. Новые багфиксы (включая Wayland-специфичные) выпускаются только для Qt 6.
> - Строго типизированные enum’ы (`Qt.AlignmentFlag.AlignCenter`) — лучшая поддержка IDE.

---

## 1. Аудит текущих X11-зависимостей

### Привязано к X11 (требует замены)

| Компонент | Файл | X11-зависимость | Что делает |
|-----------|------|-----------------|------------|
| **X11XKBAdapter** | `platform/xkb_adapter.py` | `libX11` ctypes (XkbGetState, XkbLockGroup, XkbKeycodeToKeysym) | Получение/переключение раскладки, keycode→char |
| **X11SelectionAdapter** | `platform/selection_adapter.py` | `python-xlib` (XGetSelectionOwner) | Определение владельца PRIMARY selection |
| **SubprocessSystemAdapter** | `platform/subprocess_impl.py` | `xdotool` (subprocess) | Симуляция клавиш (Ctrl+V и др.) |
| **SubprocessSystemAdapter** | `platform/subprocess_impl.py` | `xclip` (subprocess) | Чтение/запись буфера обмена |

### Уже работает на Wayland (без изменений)

| Компонент | Механизм |
|-----------|----------|
| **VirtualKeyboard** (`input/virtual_keyboard.py`) | `evdev.UInput` — уровень ядра Linux, работает везде |
| **DeviceManager** (`input/device_manager.py`) | `evdev` — уровень ядра |
| **UdevMonitor** (`input/udev_monitor.py`) | `pyudev` — уровень ядра |
| **Intelligence** (`intelligence/*`) | Чистый Python |
| **Core** (`core/*`) | Чистый Python |
| **UI/Tray** (`ui/*`) | PyQt5 → **PyQt6** — полный переход, Wayland-first |

### Существующие абстракции (наше преимущество)

Архитектура LSwitch 2.0 уже содержит интерфейсы, позволяющие подменять реализации:
- `IXKBAdapter` — `get_layouts()`, `get_current_layout()`, `switch_layout()`, `keycode_to_char()`
- `ISelectionAdapter` — `get_selection()`, `has_fresh_selection()`, `replace_selection()`
- `ISystemAdapter` — `get_clipboard()`, `set_clipboard()`, `xdotool_key()`

Wayland-адаптеры реализуют те же интерфейсы → Core/Intelligence/UI слои не меняются.

---

## 2. Архитектура решения

### 2.1. Фабрика платформы: `PlatformFactory`

```
app.py: _init_platform()
  │
  ├─ detect_session_type()          # XDG_SESSION_TYPE → "x11" | "wayland"
  │
  ├─ X11:
  │    ├─ SystemAdapter      → SubprocessSystemAdapter (xclip, xdotool)
  │    ├─ XKBAdapter         → X11XKBAdapter (libX11 ctypes)
  │    └─ SelectionAdapter   → X11SelectionAdapter (python-xlib)
  │
  └─ Wayland:
       ├─ detect_compositor()       # XDG_CURRENT_DESKTOP → gnome|kde|sway|hyprland
       │
       ├─ SystemAdapter      → WaylandSystemAdapter
       │    ├── clipboard: QClipboard (PyQt6, нативный Wayland-клиент)
       │    │   └── fallback (headless): wl-copy / wl-paste (subprocess)
       │    └── xdotool_key: через VirtualKeyboard.send_combo() (evdev.UInput)
       │
       ├─ XKBAdapter         → CompositorXKBAdapter (dispatcher)
       │    ├── KdeLayoutBackend     — QtDBus (PyQt6.QtDBus, полноценный на Qt6)
       │    ├── GnomeLayoutBackend   — Gio.Settings / PyGObject
       │    ├── SwayLayoutBackend    — Unix-сокет: i3ipc / swaymsg IPC
       │    ├── HyprlandLayoutBackend — Unix-сокет: $HYPRLAND_INSTANCE_SIGNATURE
       │    └── keycode_to_char()    — libxkbcommon ctypes (keycode→char)
       │        └── Конвертация char→char (EN↔RU) — maps.py (другая задача)
       │
       └─ SelectionAdapter   → WaylandSelectionAdapter
            ├── get_selection()      — QClipboard (mode=Selection)
            ├── has_fresh_selection() — сигнал QClipboard::selectionChanged()
            ├── replace_selection()  — QClipboard::setText() + UInput Ctrl+V
            └── expand_selection()   — UInput Ctrl+Shift+Left
```

### 2.2. Принципы

1. **Qt6-first для IPC и clipboard.** PyQt6 — основной GUI-фреймворк. `QClipboard` на Wayland работает как нативный Wayland-клиент (Qt 6 — Wayland-first). `QtDBus` в PyQt6 полностью исправлен (в отличие от багов PyQt5). subprocess (`wl-clipboard`) — только fallback для headless-режима.
2. **Нативный IPC для горячего пути.** Переключение раскладки (при каждом двойном Shift) — через `PyQt6.QtDBus` / Unix-сокеты. Без fork/exec.
3. **Событийная модель вместо поллинга.** PRIMARY selection отслеживается через сигнал `QClipboard::selectionChanged()` вместо таймера 500мс или ненадёжного `wl-paste --watch`.
4. **Симуляция клавиш — UInput.** `VirtualKeyboard.send_combo()` (evdev.UInput) заменяет `xdotool` на обеих платформах. Работает на уровне ядра — универсально. UInput уже обязателен для retype-режима.
5. **`maps.py` и `libxkbcommon` — разные задачи.** `maps.py` — конвертация char→char (EN↔RU), полная и проверенная тестами. `libxkbcommon` — конвертация keycode→char (замена X11 XkbKeycodeToKeysym). Оба нужны, но не взаимозаменяемы.
6. **Threading-модель Qt 6.** `QtDBus` и `QClipboard` работают только из потока с `QEventLoop`. Вызовы из evdev-потока пробрасываются через `QMetaObject.invokeMethod(..., Qt.ConnectionType.QueuedConnection)` или сигнал-слот.

---

## 3. Детали реализации каждого компонента

### 3.1. `WaylandSystemAdapter` (реализует `ISystemAdapter`)

Замена `SubprocessSystemAdapter` для Wayland-сессий.

**Clipboard** — через `QClipboard` (основной путь):

Qt на Wayland работает как нативный Wayland-клиент. `QClipboard` напрямую взаимодействует с compositor через `wl_data_device` / `zwp_primary_selection_device` без fork/exec. Это исключает race conditions и буферизационные задержки subprocess-обёрток.

| Метод | Реализация |
|-------|-----------|
| `get_clipboard("primary")` | `QApplication.clipboard().text(QClipboard.Selection)` |
| `get_clipboard("clipboard")` | `QApplication.clipboard().text(QClipboard.Clipboard)` |
| `set_clipboard(text, "clipboard")` | `QApplication.clipboard().setText(text, QClipboard.Clipboard)` |
| `set_clipboard(text, "primary")` | `QApplication.clipboard().setText(text, QClipboard.Selection)` |

> **Fallback (headless-режим без Qt):** `wl-paste -p -n` / `wl-copy` через subprocess — для systemd-сервиса без GUI.

> **⚠️ Threading:** `QClipboard` работает только из главного потока Qt. Вызовы из evdev-потока пробрасываются через `QMetaObject.invokeMethod(..., Qt.BlockingQueuedConnection)` для синхронного получения результата.

**Симуляция клавиш** — через `VirtualKeyboard`:

| Метод | Реализация |
|-------|-----------|
| `xdotool_key("ctrl+v")` | `VirtualKeyboard`: press KEY_LEFTCTRL → press KEY_V → release KEY_V → release KEY_LEFTCTRL |
| `xdotool_key("ctrl+shift+Left")` | Аналогично, через серию UInput write() |

Нужен маппинг строковых имён клавиш → evdev keycodes:
```python
_KEY_MAP = {
    "ctrl": ecodes.KEY_LEFTCTRL,
    "shift": ecodes.KEY_LEFTSHIFT,
    "alt": ecodes.KEY_LEFTALT,
    "super": ecodes.KEY_LEFTMETA,
    "Left": ecodes.KEY_LEFT,
    "Right": ecodes.KEY_RIGHT,
    "BackSpace": ecodes.KEY_BACKSPACE,
    "Return": ecodes.KEY_ENTER,
    "v": ecodes.KEY_V,
    "c": ecodes.KEY_C,
    "a": ecodes.KEY_A,
    ...
}
```

**Файл:** `lswitch/platform/wayland_system_adapter.py`

### 3.2. `WaylandSelectionAdapter` (реализует `ISelectionAdapter`)

**Ключевое отличие от X11:** в Wayland нет `owner_id` (ID окна-владельца выделения). Freshness определяется через событийную модель Qt.

#### Freshness через `QClipboard::selectionChanged`

~~Ранее планировался `wl-paste --primary --watch cat`, но этот подход ненадёжен: многострочный текст ломает разделение событий (нет разделителя между выводами разных вызовов `cat`).~~

Используем сигнал Qt `selectionChanged()` — он срабатывает ровно один раз при каждом изменении PRIMARY selection, независимо от количества строк. PyQt6 на Wayland работает как нативный Wayland-клиент и корректно обрабатывает протокол `wp_primary_selection`.

```python
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QClipboard
from PyQt6.QtCore import QObject, Qt

class WaylandSelectionAdapter(QObject, ISelectionAdapter):
    def __init__(self, system: ISystemAdapter):
        super().__init__()
        self._system = system
        self._clipboard = QApplication.clipboard()
        self._latest_text: str = ""
        self._text_changed: bool = False
        self._lock = threading.Lock()
        # Qt-сигнал — событийная модель вместо поллинга
        self._clipboard.selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        """Слот Qt — вызывается при каждом изменении PRIMARY selection."""
        text = self._clipboard.text(QClipboard.Mode.Selection)
        with self._lock:
            if text != self._latest_text:
                self._latest_text = text
                self._text_changed = True

    def get_selection(self) -> SelectionInfo:
        with self._lock:
            return SelectionInfo(
                text=self._latest_text,
                owner_id=0,             # не используется на Wayland
                timestamp=time.time(),
            )

    def has_fresh_selection(self) -> bool:
        with self._lock:
            fresh = self._text_changed and bool(self._latest_text)
            self._text_changed = False
            return fresh
```

**`replace_selection`:** `QClipboard.setText()` + UInput Ctrl+V (через `VirtualKeyboard.send_combo()`). `QClipboard.setText()` синхронно регистрирует data source в compositor — race condition исключён.
**`expand_selection_to_word`:** UInput Ctrl+Shift+Left (через `VirtualKeyboard.send_combo()`).

**Файл:** `lswitch/platform/wayland_selection_adapter.py`

### 3.3. `CompositorXKBAdapter` (реализует `IXKBAdapter`)

Dispatcher, который определяет композитор при инициализации и делегирует конкретному backend-у.

#### Определение композитора

```python
def detect_compositor() -> str:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in desktop or "unity" in desktop or "cinnamon" in desktop:
        return "gnome"
    if "kde" in desktop or "plasma" in desktop:
        return "kde"
    if os.environ.get("SWAYSOCK"):
        return "sway"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    return "unknown"
```

#### GNOME: D-Bus backend

Подключение через `Gio.Settings` (PyGObject) или `dbus-next`:

| Метод | D-Bus путь |
|-------|-----------|
| `get_layouts()` | `org.gnome.desktop.input-sources` → ключ `sources` |
| `get_current_layout()` | `org.gnome.desktop.input-sources` → ключ `current` |
| `switch_layout(target)` | `org.gnome.desktop.input-sources` → set `current` = target.index |

Через PyGObject (уже доступен в GNOME-среде):
```python
from gi.repository import Gio
settings = Gio.Settings.new("org.gnome.desktop.input-sources")
current = settings.get_uint("current")   # мгновенно, без subprocess
settings.set_uint("current", new_index)  # мгновенно
```

#### KDE Plasma: QtDBus backend (нативный, без subprocess)

~~Ранее планировался subprocess-вызов `qdbus6` с переходом на нативный D-Bus на отдельной фазе.~~
PyQt6 обеспечивает полноценный `QtDBus` (в отличие от PyQt5, где `QDBusInterface.call()` возвращал невалидные сообщения). Реализация без накладных расходов на fork/exec (10–50 мс на вызов).

| Метод | QtDBus вызов |
|-------|-----------|
| `get_current_layout()` | `QDBusInterface("org.kde.keyboard", "/Layouts", "org.kde.KeyboardLayouts").call("getLayout")` |
| `switch_layout(target)` | `setLayout(u)->b` через typed D-Bus `uint32`; fallback: циклически вызвать `switchToNextLayout` до нужного индекса и проверить `getLayout` |
| `get_layouts()` | `QDBusInterface(...).call("getLayoutsList")` |

> **Plasma compatibility note:** на проверенной KDE Wayland session чтение
> (`getLayoutsList`, `getLayout`) работает, а `setLayout` виден в introspection,
> но прежние вызовы с signatures `i`, `s`, `ss` не подходят: API ожидает
> `setLayout(u)->b`. Поэтому реализация передает typed D-Bus `uint32`,
> диагностирует реальные methods/signatures через D-Bus introspection и имеет
> fallback через `switchToNextLayout`.

> **⚠️ Threading:** `QtDBus` работает только из потока с `QEventLoop` (главный поток Qt). Вызовы из evdev-потока пробрасываются через `QMetaObject.invokeMethod(..., Qt.ConnectionType.BlockingQueuedConnection)` для синхронного результата.

#### Sway: IPC-сокет backend

Через библиотеку `i3ipc` (чистый Python, стабильный API):
```python
import i3ipc
conn = i3ipc.Connection()
# get_inputs() → найти keyboard → xkb_active_layout_index
# command("input type:keyboard xkb_switch_layout N")
```

Или напрямую через Unix-сокет `$SWAYSOCK` (без зависимостей).

#### Hyprland: Unix-сокет backend

Прямое чтение/запись в сокет:
- `$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock`
- Запрос: `dispatch switchxkblayout <device> <index>`

#### `keycode_to_char()` — libxkbcommon (замена X11 XkbKeycodeToKeysym)

`libxkbcommon` используется всеми Wayland-композиторами. Через ctypes:
```python
libxkbcommon = ctypes.cdll.LoadLibrary("libxkbcommon.so.0")
# xkb_keymap_new_from_names() → создать keymap для "us" и "ru"
# xkb_state_key_get_one_sym() → keycode → keysym
# xkb_keysym_to_utf32() → keysym → unicode char
```

> **Важно: `libxkbcommon` и `maps.py` решают разные задачи.**
> - `libxkbcommon` → **keycode→char** (замена X11-функции `XkbKeycodeToKeysym`). Нужен для `keycode_to_char()` в Wayland-среде.
> - `maps.py` → **char→char** (конвертация `EN_TO_RU` / `RU_TO_EN`). Это полная, проверенная тестами таблица для основной пары языков. Не заменяется `libxkbcommon`.
>
> Оба компонента нужны и дополняют друг друга. `maps.py` — не техдолг, а осознанный выбор для стабильной конвертации EN↔RU. `libxkbcommon` расширяет поддержку кастомных раскладок в будущем (Dvorak, Colemak, типографские раскладки).

**Файлы:**
- `lswitch/platform/wayland_xkb_adapter.py` — `CompositorXKBAdapter` + dispatch
- `lswitch/platform/wayland_backends/gnome.py`
- `lswitch/platform/wayland_backends/kde.py`
- `lswitch/platform/wayland_backends/sway.py`
- `lswitch/platform/wayland_backends/hyprland.py`

---

## 4. Изменения в `app.py`

Текущий `_init_platform()` жёстко создаёт X11-адаптеры. Нужна ветка:

```python
def _init_platform(self):
    session = detect_session_type()  # "x11" | "wayland"

    if session == "wayland":
        from lswitch.platform.wayland_system_adapter import WaylandSystemAdapter
        from lswitch.platform.wayland_selection_adapter import WaylandSelectionAdapter
        from lswitch.platform.wayland_xkb_adapter import CompositorXKBAdapter

        self.virtual_kb = VirtualKeyboard(debug=self.debug)
        self.system = WaylandSystemAdapter(virtual_kb=self.virtual_kb, debug=self.debug)
        self.selection = WaylandSelectionAdapter(system=self.system, debug=self.debug)
        self.xkb = CompositorXKBAdapter(debug=self.debug)
    else:
        # существующая X11-логика без изменений
        from lswitch.platform.subprocess_impl import SubprocessSystemAdapter
        self.system = SubprocessSystemAdapter(debug=self.debug)
        self.xkb = X11XKBAdapter(debug=self.debug)
        self.selection = X11SelectionAdapter(system=self.system, debug=self.debug)
        self.virtual_kb = VirtualKeyboard(debug=self.debug)

    # дальше — общий код (Intelligence, ConversionEngine, EventManager, etc.)
```

### Замена `_SelectionLoggerThread` на Wayland

На X11 — текущий поллинг каждые 500мс через `_SelectionLoggerThread`.
На Wayland — `WaylandSelectionAdapter` сам запускает `wl-paste --watch` и отслеживает изменения в фоновом потоке. `_SelectionLoggerThread` **не нужен** для Wayland.

```python
if session != "wayland":
    self._selection_logger = _SelectionLoggerThread(self.selection, ...)
    self._selection_logger.start()
# На Wayland watcher уже встроен в WaylandSelectionAdapter
```

---

## 5. Структура новых файлов

```
lswitch/platform/
├── __init__.py
├── clipboard.py                    # (deprecated)
├── platform_factory.py             # NEW: detect_session_type(), detect_compositor()
├── selection_adapter.py            # ISelectionAdapter + X11SelectionAdapter
├── subprocess_impl.py              # SubprocessSystemAdapter (X11)
├── system_adapter.py               # ISystemAdapter
├── xkb_adapter.py                  # IXKBAdapter + X11XKBAdapter
├── xkb_bindings.py                 # ctypes structs для X11
├── wayland_system_adapter.py       # NEW: WaylandSystemAdapter
├── wayland_selection_adapter.py    # NEW: WaylandSelectionAdapter
├── wayland_xkb_adapter.py          # NEW: CompositorXKBAdapter + dispatch
└── wayland_backends/               # NEW: compositor-specific layout backends
    ├── __init__.py
    ├── base.py                     #   ILayoutBackend interface
    ├── gnome.py                    #   GnomeLayoutBackend (D-Bus / Gio)
    ├── kde.py                      #   KdeLayoutBackend (D-Bus)
    ├── sway.py                     #   SwayLayoutBackend (IPC socket)
    └── hyprland.py                 #   HyprlandLayoutBackend (Unix socket)
```

---

## 6. Зависимости

### Python-пакеты

| Пакет | Для чего | Обязательность |
|-------|---------|---------------|
| `evdev` | UInput, чтение устройств, `send_combo()` | Обязательно (уже есть) |
| `pyudev` | Hot-plug | Обязательно (уже есть) |
| `PyQt6` | GUI, QClipboard, QtDBus (замена PyQt5) | **Обязательно** |
| `PyGObject` (`gi`) | GNOME D-Bus (Фаза 5+) | Опционально (follow-up) |
| `i3ipc` | Sway IPC (Фаза 5+) | Опционально (follow-up) |

> **Миграция PyQt5 → PyQt6 (breaking changes):**
> - Enum scope: `Qt.AlignCenter` → `Qt.AlignmentFlag.AlignCenter`, `QFont.Bold` → `QFont.Weight.Bold`
> - `QAction` переехал: `PyQt5.QtWidgets.QAction` → `PyQt6.QtGui.QAction`
> - `exec_()` → `exec()`
> - `QHeaderView.Stretch` → `QHeaderView.ResizeMode.Stretch`
> - Все `from PyQt5` → `from PyQt6` (7 файлов в `lswitch/ui/` + `app.py`)
>
> **Установка:** `pip install PyQt6` или `sudo apt install python3-pyqt6` (Ubuntu 24.04+, Arch, Fedora).

### Системные утилиты

| Утилита | Пакет | Для чего | Фаза |
|---------|-------|---------|------|
| `wl-copy`, `wl-paste` | `wl-clipboard` | Fallback clipboard для headless | 1 (fallback) |

---

## 7. План реализации (KDE-first, Qt6-native)

> **Стратегия:** Полный переход на PyQt6 без compatibility-слоёв. PyQt6 даёт рабочий `QtDBus`, стабильный `QClipboard` (Wayland-first) и `selectionChanged()`. Первый целевой композитор — KDE Plasma. `maps.py` — для char→char (EN↔RU), `libxkbcommon` — для keycode→char.

### Фаза 0: Миграция PyQt5 → PyQt6 + Фундамент

**Блокер:** Без PyQt6 невозможен рабочий `QtDBus` для KDE backend.

**Миграция UI (7 файлов):**
- [ ] `lswitch/app.py` — `from PyQt5` → `from PyQt6`, `exec_()` → `exec()`
- [ ] `lswitch/ui/tray_icon.py` — `from PyQt6`, обновить enum scope
- [ ] `lswitch/ui/context_menu.py` — `QAction` переехал в `PyQt6.QtGui`
- [ ] `lswitch/ui/config_dialog.py` — `from PyQt6`, enum scope
- [ ] `lswitch/ui/debug_monitor.py` — `from PyQt6`, `QHeaderView.ResizeMode.Stretch`, enum scope
- [ ] `lswitch/ui/adapters/kde.py` — `from PyQt6`
- [ ] `lswitch/ui/adapters/cinnamon.py` — `from PyQt6`, `QAction` → `PyQt6.QtGui`
- [ ] `setup.py` — `extras_require: 'gui': ['PyQt6']`
- [ ] `requirements.txt`, `README.md` — PyQt5 → PyQt6
- [ ] Тесты UI — убедиться, что mock-и корректны с PyQt6 enum scope

**Фундамент Wayland:**
- [ ] `VirtualKeyboard.send_combo(keys)` — отправка произвольных комбинаций (Ctrl+V, Ctrl+Shift+Left и т.д.)
  - Принимает строку вида `"ctrl+v"`, `"ctrl+shift+Left"`
  - Маппинг строковых имён → evdev keycodes
  - Press модификаторов → press основной клавиши → release в обратном порядке
  - Настраиваемые задержки между событиями (как в существующем `tap_key`)
- [ ] `platform_factory.py` — `detect_session_type()`, `detect_compositor()`
  - `XDG_SESSION_TYPE` → `"x11"` | `"wayland"`
  - `XDG_CURRENT_DESKTOP` / env vars → `"kde"` | `"gnome"` | `"sway"` | `"hyprland"` | `"unknown"`
- [ ] Тесты `send_combo` (mock UInput)
- [ ] Тесты `detect_session_type`, `detect_compositor`

### Фаза 1: WaylandSystemAdapter (Qt6-native clipboard)

Реализует `ISystemAdapter`. Clipboard через `QClipboard` (Qt 6, нативный Wayland-клиент), симуляция клавиш через `send_combo`.

- [ ] `wayland_system_adapter.py`
  - `get_clipboard(selection)` → `QApplication.clipboard().text(QClipboard.Mode.Selection/Clipboard)`
  - `set_clipboard(text, selection)` → `QApplication.clipboard().setText(text, mode)`
  - `xdotool_key(sequence)` → делегация в `VirtualKeyboard.send_combo()`
  - `run_command(args, timeout)` → без изменений (общий subprocess)
  - Threading bridge: `QMetaObject.invokeMethod(..., Qt.ConnectionType.BlockingQueuedConnection)`
- [ ] Fallback для headless: `wl-paste` / `wl-copy` через subprocess (без Qt)
- [ ] Тесты (mock QClipboard + mock VirtualKeyboard)

### Фаза 2: WaylandSelectionAdapter (Qt6-native событийная модель)

Реализует `ISelectionAdapter`. Сигнал `QClipboard::selectionChanged()` вместо поллинга и `wl-paste --watch`.

- [ ] `wayland_selection_adapter.py`
  - `get_selection()` → `QClipboard.text(QClipboard.Mode.Selection)` (из главного потока)
  - `has_fresh_selection()` → `_text_changed` флаг, устанавливаемый слотом `selectionChanged`
  - `replace_selection(new_text)` → `QClipboard.setText()` + `send_combo("ctrl+v")` (race condition исключён — Qt 6 синхронно регистрирует data source)
  - `expand_selection_to_word()` → `send_combo("ctrl+shift+Left")`
- [ ] Корректный lifecycle: disconnect сигнала в `close()`
- [ ] Тесты

### Фаза 3: KDE XKB Backend (PyQt6.QtDBus, нативный D-Bus)

Layout switching через `QDBusInterface` — полноценный `QtDBus` из PyQt6 (без багов PyQt5).

- [ ] `wayland_backends/base.py` — `ILayoutBackend` интерфейс
  ```python
  class ILayoutBackend(ABC):
      def get_layouts(self) -> list[LayoutInfo]: ...
      def get_current_layout(self) -> LayoutInfo: ...
      def switch_layout(self, target: LayoutInfo) -> None: ...
  ```
- [ ] `wayland_backends/kde.py` — `KdeLayoutBackend`
  - `from PyQt6.QtDBus import QDBusInterface, QDBusConnection`
  - `get_current_layout()` → `QDBusInterface("org.kde.keyboard", "/Layouts", ...).call("getLayout")`
  - `switch_layout(target)` → `setLayout(u)->b` with typed D-Bus `uint32`, then
    `switchToNextLayout` cycle fallback with final `getLayout` verification
  - `get_layouts()` → `.call("getLayoutsList")`
  - Diagnostics: D-Bus introspection shows actual `/Layouts` methods/signatures
  - Threading bridge: все вызовы проходят через главный поток Qt
- [ ] `wayland_xkb_adapter.py` — `CompositorXKBAdapter` (dispatcher)
  - Определяет compositor через `detect_compositor()`
  - Делегирует конкретному backend
  - `keycode_to_char()` → через `libxkbcommon` ctypes (замена X11 XkbKeycodeToKeysym)
- [ ] Тесты (mock QDBusInterface)

### Фаза 4: Интеграция в app.py

- [ ] Ветвление в `_init_platform()` по `detect_session_type()`
  - Wayland: `WaylandSystemAdapter`, `WaylandSelectionAdapter`, `CompositorXKBAdapter`
  - X11: без изменений
- [ ] Отключение `_SelectionLoggerThread` для Wayland (событийная модель Qt встроена в `WaylandSelectionAdapter`)
- [ ] Обновить проверку сессии (убрать жёсткое требование `DISPLAY`)
- [ ] Проверка прав UInput при запуске: понятное сообщение при `PermissionError` (группа `input`, udev-правила)
- [ ] Интеграционные тесты на KDE Wayland
- [ ] Ручная проверка: double-Shift → конвертация в retype/selection/selection_expand режимах

### Фаза 5+ (follow-up): Другие композиторы

- [ ] `wayland_backends/gnome.py` — Gio.Settings (D-Bus: `org.gnome.desktop.input-sources`)
- [ ] `wayland_backends/sway.py` — `i3ipc` / Unix-сокет (`$SWAYSOCK`)
- [ ] `wayland_backends/hyprland.py` — Unix-сокет (`$HYPRLAND_INSTANCE_SIGNATURE`)
- [ ] Graceful fallback при неизвестном композиторе (информативное сообщение)
- [ ] CI с headless Wayland-композитором (weston / headless sway)
- [ ] Обновить `config/lswitch.service` — убрать жёсткую привязку к X11
- [ ] Обновить `docs/USAGE.md` — инструкции для Wayland
