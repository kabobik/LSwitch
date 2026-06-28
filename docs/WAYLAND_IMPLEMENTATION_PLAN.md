# Wayland implementation plan

Дата: 2026-06-28

Этот файл - рабочий план Wayland-порта LSwitch. Он должен быть source of truth для реализации. Исторические заметки, гипотезы и спорные исследования остаются в `docs/WAYLAND_RESEARCH.md`.

## 1. Цель

Полноценно запустить LSwitch в Wayland-сессии без XWayland-зависимостей для основных сценариев:

- retype mode: удалить набранное слово, переключить раскладку, воспроизвести события через UInput;
- auto-conversion по Space;
- selection mode: конвертация выделенного текста;
- selection-expand fallback: двойной Shift без буфера пытается расширить выделение до слова;
- GUI/tray и headless/service режимы.

Первый целевой compositor: KDE Plasma Wayland. Остальные compositors идут после KDE MVP.

## 2. Текущее состояние кода

Работает без привязки к X11:

- `lswitch/core/*` - state machine, modes, event bus, conversion engine;
- `lswitch/intelligence/*` - словари, n-gram, auto detector;
- `lswitch/input/device_manager.py` - чтение evdev устройств;
- `lswitch/input/virtual_keyboard.py` - UInput replay/tap.
- `lswitch/app.py` получает готовый `PlatformAdapters` и не ветвится по X11/Wayland.

Привязано к X11:

- `lswitch/platform/xkb_adapter.py` использует `libX11`, `setxkbmap`, Cinnamon `gdbus`;
- `lswitch/platform/selection_adapter.py` использует X11 PRIMARY owner через `python-xlib`;
- `lswitch/platform/subprocess_impl.py` использует `xdotool` и `xclip`;
- UI и runtime уже переведены на PyQt6;
- `config/lswitch.service` содержит X11-oriented environment.

Важная уже существующая опора: интерфейсы `IXKBAdapter`, `ISelectionAdapter`, `ISystemAdapter` позволяют добавить Wayland implementations без переписывания core.

## 3. Главные блокеры

### 3.1. Platform bootstrap должен оставаться единственной OS/session границей

`LSwitchApp._init_platform()` уже вызывает factory, а `LSwitchApp.run()` не проверяет session/env напрямую. X11/Wayland выбор должен оставаться только в `platform_factory.py`.

Решение:

- `platform_factory.py` добавлен;
- `detect_session_type()` реализован по `XDG_SESSION_TYPE`, `WAYLAND_DISPLAY`, `DISPLAY`;
- `detect_compositor()` реализован по `XDG_CURRENT_DESKTOP`, `KDE_FULL_SESSION`, `SWAYSOCK`, `HYPRLAND_INSTANCE_SIGNATURE`;
- X11 ветка оставлена максимально неизменной;
- Wayland ветка возвращает skeleton adapters и fail-fast ошибки на конкретных backend operations.

### 3.2. Qt objects вызываются из evdev thread

В GUI-режиме Qt event loop живет в main thread, а evdev loop и conversion вызываются в background thread. В headless-режиме Qt event loop сейчас не создается.

Wayland clipboard и QtDBus нельзя надежно дергать напрямую из evdev thread.

Решение:

- ввести `QtBridge`/`MainThreadInvoker` с синхронным `call()` через Qt queued signal;
- все `QClipboard` и `QtDBus` операции проводить через этот bridge;
- для Wayland headless выбрать явную модель:
  - preferred: минимальный `QGuiApplication`/`QApplication` + evdev worker thread;
  - fallback: subprocess-only путь для clipboard/layout backend там, где Qt недоступен.

### 3.3. PyQt6 runtime нужен Wayland/KDE backend-у

KDE-native D-Bus планируется через QtDBus, поэтому UI/runtime должны оставаться на PyQt6.

Решение:

- GUI уже мигрирован на PyQt6;
- imports и enum scopes обновлены;
- `QAction` берется из `PyQt6.QtGui`;
- `exec_()` заменен на `exec()`;
- `setup.py`, `requirements.txt`, README обновлены.

### 3.4. Layout switching compositor-specific

На Wayland нет универсального XKB API уровня X11 для получения и переключения текущей раскладки активной сессии.

Решение:

- создать `CompositorXKBAdapter`;
- backend interface:
  - `get_layouts() -> list[LayoutInfo]`;
  - `get_current_layout() -> LayoutInfo`;
  - `switch_layout(target: LayoutInfo | None) -> LayoutInfo`;
- KDE first backend через D-Bus;
- GNOME/Sway/Hyprland позже отдельными backend-ами;
- `keycode_to_char()` реализовать через `libxkbcommon` или через reliable local mapping fallback для `us`/`ru` MVP.

### 3.5. Selection mode нельзя переносить как X11 PRIMARY

На X11 свежесть выделения определяется через `(owner_id, text)`. На Wayland нет X11 owner id, а `QClipboard.Selection`/primary selection нельзя считать гарантированным для всех compositors и Qt builds.

Решение:

- основной Wayland selection flow делать через активное приложение:
  1. сохранить clipboard;
  2. отправить `Ctrl+C` через UInput;
  3. прочитать clipboard;
  4. сконвертировать текст;
  5. записать clipboard;
  6. отправить `Ctrl+V`;
  7. восстановить clipboard с задержкой/guard-ом;
- `QClipboard.Selection` использовать только как optional fast path при `supportsSelection()` и ручном подтверждении;
- `owner_id=0` считать нормой для Wayland.

### 3.6. `xdotool` и `xclip` не работают как Wayland primitives

X11 adapter сейчас отправляет комбинации через `xdotool`, clipboard идет через `xclip`.

Решение:

- добавить `VirtualKeyboard.send_combo(sequence: str)`;
- в `WaylandSystemAdapter.send_key_sequence()` делегировать в `send_combo()`;
- для clipboard использовать `QClipboard` через Qt bridge;
- subprocess fallback: `wl-copy`/`wl-paste`, только когда Qt path невозможен.

### 3.7. Service environment

Systemd unit сейчас содержит `XAUTHORITY`, но не Wayland/DBus runtime переменные.

Решение:

- обновить `config/lswitch.service`;
- документировать импорт `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`, `XDG_CURRENT_DESKTOP`;
- при старте давать понятную ошибку по UInput permissions и отсутствующим env vars.

## 4. Выбранная архитектура

```
LSwitchApp
  |
  +-- platform_factory.create_platform_adapters()
  |
  +-- X11
  |     +-- SubprocessSystemAdapter  # existing xclip/xdotool
  |     +-- X11XKBAdapter            # existing libX11
  |     +-- X11SelectionAdapter      # existing python-xlib
  |
  +-- Wayland
        +-- WaylandSystemAdapter     # skeleton now, QClipboard + UInput combos later
        +-- WaylandSelectionAdapter  # skeleton now, copy/paste selection flow later
        +-- WaylandLayoutAdapter     # skeleton now, compositor backend later
        +-- QtBridge                 # main-thread Qt calls, next phase
        +-- CompositorLayoutBackend
              +-- KdeLayoutBackend
              +-- GnomeLayoutBackend       # follow-up
              +-- SwayLayoutBackend        # follow-up
              +-- HyprlandLayoutBackend    # follow-up
              +-- XkbCommonKeyMapper
```

Принцип: core не знает о Wayland. Все platform differences остаются в adapters.

## 4.1. Принятые решения для MVP

- Wayland `--headless` использует тот же PyQt6 runtime и Qt event loop, что и GUI-режим, но не создает tray. Headless на Wayland означает "без видимого UI", а не "без Qt".
- `wl-copy`/`wl-paste` остаются fallback/diagnostic path, но не default implementation.
- Вводим нейтральный adapter API `send_key_sequence(sequence)`. Старый `xdotool_key(sequence)` остается deprecated alias на время миграции и для совместимости тестов/старого кода.
- KDE Wayland MVP гарантирует `us`/`ru` first. Backend может видеть больше layouts, но arbitrary XKB layouts не являются обещанием первого релиза.
- Добавляем advanced config `wayland_selection_strategy`, default `"auto"`. Для MVP `"auto"` фактически выбирает безопасный Clipboard copy/paste flow. Возможные значения: `"auto"`, `"clipboard_copy"`, `"primary_selection"`, `"disabled"`.
- Основной запуск на Wayland: один процесс `lswitch` с Qt loop, tray и evdev worker. `lswitch --headless` - optional service/tiling-WM mode того же процесса. Service не является отдельным обязательным backend-daemon.

## 5. Небезопасные предположения из research notes

Эти пункты нельзя использовать как безусловную основу реализации:

- `QClipboard.Selection` на Wayland работает всегда. Нужен feature detection и fallback.
- `selectionChanged()` достаточно для freshness. На Wayland freshness лучше завязать на явный `Ctrl+C` flow или compositor-specific primary support.
- Headless может пользоваться `QClipboard` без Qt event loop. Нужен Qt loop или subprocess fallback.
- KDE D-Bus API можно зашить без проверки. Backend должен валидировать service/object/interface/method at startup и логировать понятную ошибку.
- `libxkbcommon` сам знает текущую compositor раскладку. Он умеет keymap/state, но актуальную раскладку все равно надо получать из compositor backend.

## 6. Фазы реализации

### Фаза 0. Подготовка и тестовая сетка

- [x] Зафиксировать тестовые сценарии для X11, чтобы порт не сломал текущую работу.
- [x] Добавить unit tests для platform detection.
- [x] Добавить fake/mock tests для future Wayland adapters.
- [x] Обновить документацию: `WAYLAND_RESEARCH.md` = notes, этот файл = plan.

Готовность: тесты проходят, X11 behavior не изменен.

### Фаза 1. PyQt6 migration

- [x] Перенести UI imports с PyQt5 на PyQt6.
- [x] Исправить enum scopes.
- [x] Перенести `QAction` в `QtGui`.
- [x] Заменить `exec_()` на `exec()`.
- [x] Обновить packaging.

Готовность: GUI/tray стартует на X11 с PyQt6, existing tests проходят.

### Фаза 2. UInput combo API

- Добавить `VirtualKeyboard.send_combo()` и adapter-level `send_key_sequence()`.
- Поддержать минимум:
  - `ctrl+c`;
  - `ctrl+v`;
  - `ctrl+shift+left`;
  - `backspace`, `space`, `enter`;
  - aliases: `Left`, `BackSpace`, `Return`.
- Добавить tests с mocked UInput write order.

Готовность: `send_combo("ctrl+v")` генерирует press/release в правильном порядке.

### Фаза 3. Platform factory и Wayland runtime skeleton

- [x] Добавить `platform_factory.py`.
- [x] Добавить Wayland skeleton adapters, которые явно fail fast для еще не реализованных paths.
- [x] Встроить ветку в `_init_platform()`.
- [x] Не включать platform selection polling в Wayland mode; этот выбор должен приходить из platform factory.
- [x] Убрать прямой session/env check из `LSwitchApp.run()`.

Готовность: приложение в Wayland хотя бы стартует до понятной ошибки backend-а, X11 продолжает работать.

### Фаза 4. QtBridge и lifecycle

- Создать Qt app до инициализации Wayland adapters.
- Ввести `QtBridge.call()`.
- Перевести clipboard/DBus access на main thread.
- Wayland headless всегда запускает Qt loop в main thread, но не создает tray.
- Subprocess clipboard path оставлять только fallback/diagnostic mode.

Готовность: mock tests подтверждают, что Wayland adapters не трогают Qt из evdev thread.

### Фаза 5. WaylandSystemAdapter

- `get_clipboard()`/`set_clipboard()` через `QClipboard`.
- `send_key_sequence()` через `VirtualKeyboard.send_combo()`.
- `xdotool_key()` оставить deprecated alias.
- Fallback на `wl-copy`/`wl-paste` при headless/no-Qt.
- Понятные logs при недоступном clipboard.

Готовность: clipboard operations проходят в Wayland KDE session.

### Фаза 6. WaylandSelectionAdapter

- Реализовать copy/paste selection flow.
- Добавить задержки/ожидание clipboard change после `Ctrl+C`.
- Не считать empty clipboard fresh selection.
- Восстанавливать clipboard после paste аккуратно, чтобы не сломать вставку в медленных приложениях.
- Optional: `QClipboard.Selection` fast path behind feature probe.

Готовность: выделение в Qt/GTK/browser/terminal приложениях конвертируется вручную через double Shift.

### Фаза 7. KDE layout backend

- Реализовать `KdeLayoutBackend`.
- На старте проверить наличие KDE keyboard D-Bus service/interface.
- `get_layouts()`, `get_current_layout()`, `switch_layout()`.
- Добавить cache с invalidation, если возможно.
- Реализовать fallback/error message, если KDE API отличается.

Готовность: retype и auto-conversion переключают раскладку на KDE Wayland.

### Фаза 8. `keycode_to_char()` на Wayland

- Реализовать `XkbCommonKeyMapper`.
- Для MVP можно поддержать `us`/`ru` reliably.
- Учитывать evdev keycode offset, shift level, layout index.
- Покрыть tests для букв и RU punctuation keys (`б`, `ю`, `ж`, `э`).

Готовность: `_extract_last_word_events()` корректно видит русские слова на Wayland.

### Фаза 9. Manual QA на KDE Wayland

Проверить:

- запуск GUI/tray;
- запуск headless/service;
- double Shift retype EN->RU и RU->EN;
- auto-conversion на Space;
- repeat double Shift/sticky buffer;
- selection conversion;
- selection-expand fallback;
- Backspace hold selection mode;
- поведение при недоступном UInput;
- конфликт с системным Shift+Shift shortcut;
- clipboard restore после selection conversion.

Готовность: KDE Wayland MVP можно считать рабочим.

### Фаза 10. Follow-up compositors

- GNOME backend через GSettings/DBus.
- Sway backend через IPC.
- Hyprland backend через IPC.
- Headless CI на weston/sway, если реалистично.
- Документация по compositor-specific limitations.

## 7. Definition of done для KDE Wayland MVP

- `lswitch` стартует в KDE Wayland без X11/XWayland requirements.
- `lswitch --headless` имеет понятный поддержанный путь.
- retype mode работает для EN/RU.
- auto-conversion работает для EN/RU.
- selection mode работает хотя бы через Clipboard copy/paste flow.
- X11 regression tests проходят.
- README/service/setup обновлены.
- Ошибки окружения и permissions читаемы для пользователя.

## 8. Открытые вопросы

- Точный KDE D-Bus contract: service/object/interface/method names надо проверить runtime-интроспекцией на целевой Plasma версии.
- Clipboard restore timing после Wayland selection conversion: нужен manual QA на медленных приложениях (Electron/браузеры/IDE).
- Нужен ли отдельный config для задержек copy/paste/restore или достаточно internal constants с логированием?
