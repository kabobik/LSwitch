# LSwitch: ТЗ и план поддержки Wayland

Статус: черновик для обсуждения и дальнейшей детализации.

## 1. Цель

Добавить поддержку Wayland-сессий в LSwitch, начиная с KDE Plasma.

Основной целевой сценарий:

- пользователь запускает `lswitch` в KDE Plasma Wayland;
- LSwitch продолжает слушать двойной Shift через `evdev`;
- последнее введенное слово конвертируется через текущий механизм LSwitch;
- удаление и повторный ввод текста выполняются через `uinput`;
- текущая раскладка определяется и переключается через Wayland-совместимый backend;
- X11-поведение не ломается.

## 2. Область MVP

MVP ориентирован на KDE Plasma Wayland.

В MVP входит:

- определение типа сессии: X11 или Wayland;
- отдельная ветка инициализации платформенных адаптеров для Wayland;
- поддержка KDE Plasma backend для раскладок;
- `keycode_to_char()` без X11, через `libxkbcommon`;
- `VirtualKeyboard.send_combo()` для замены `xdotool key`;
- рабочий retype-режим в Wayland;
- аккуратный fallback для selection-режима, если PRIMARY selection недоступен;
- обновление установщика, зависимостей и документации;
- сохранение текущей X11-ветки как поддерживаемой.

В MVP не входит:

- полная поддержка GNOME, Sway, Hyprland;
- идеальная поддержка selection-режима во всех Wayland-приложениях;
- отказ от `evdev/uinput`;
- миграция всей архитектуры на portals/libei.

## 3. Важные ограничения Wayland

Wayland не предоставляет общего аналога X11-инструментов `xdotool`, `xclip`, `setxkbmap` и прямого XKB API через `libX11`.

Поэтому универсальной реализации "для всего Wayland" не получится сделать одним адаптером. Нужна архитектура:

- общий Wayland слой;
- compositor-specific backend для раскладки;
- отдельные fallback-пути для clipboard/selection;
- понятные сообщения пользователю, если compositor пока не поддержан.

## 4. Текущие X11-зависимости

Текущие компоненты, требующие замены или развилки:

| Компонент | Файл | Зависимость | Что делает |
|---|---|---|---|
| `X11XKBAdapter` | `lswitch/platform/xkb_adapter.py` | `libX11`, XKB | текущая раскладка, переключение, `keycode_to_char()` |
| `X11SelectionAdapter` | `lswitch/platform/selection_adapter.py` | `python-xlib`, X11 PRIMARY | свежесть выделения и чтение selection |
| `SubprocessSystemAdapter` | `lswitch/platform/subprocess_impl.py` | `xdotool`, `xclip` | hotkeys и clipboard |
| `app.py` | `lswitch/app.py` | жесткая X11-инициализация | всегда создает X11-адаптеры |
| `run()` | `lswitch/app.py` | сообщение только про `DISPLAY` | ошибка сформулирована как X11-only |

Компоненты, которые уже подходят для Wayland:

- `DeviceManager` и чтение клавиатуры через `evdev`;
- `VirtualKeyboard` через `evdev.UInput`;
- `UdevMonitor`;
- `core/*`;
- `intelligence/*`;
- таблицы конвертации `maps.py`;
- большая часть GUI, если зависимости Qt корректны для текущей среды.

## 5. Архитектура

### 5.1. PlatformFactory

Добавить `lswitch/platform/platform_factory.py`.

Ответственность:

- определить тип сессии по `XDG_SESSION_TYPE`;
- определить desktop/compositor по `XDG_CURRENT_DESKTOP`, `KDE_FULL_SESSION`, `SWAYSOCK`, `HYPRLAND_INSTANCE_SIGNATURE`;
- создать набор адаптеров для X11 или Wayland;
- не размазывать `if wayland` по `app.py`.

Пример целевой логики:

```python
session = detect_session_type()

if session == "wayland":
    adapters = create_wayland_adapters(debug=debug, virtual_kb=virtual_kb)
else:
    adapters = create_x11_adapters(debug=debug)
```

### 5.2. X11-ветка

Оставить текущие реализации:

- `SubprocessSystemAdapter`;
- `X11XKBAdapter`;
- `X11SelectionAdapter`.

Изменения должны быть минимальными и совместимыми с существующими тестами.

### 5.3. Wayland-ветка

Добавить:

- `lswitch/platform/wayland_system_adapter.py`;
- `lswitch/platform/wayland_selection_adapter.py`;
- `lswitch/platform/wayland_xkb_adapter.py`;
- `lswitch/platform/xkbcommon_adapter.py`;
- `lswitch/platform/wayland_backends/base.py`;
- `lswitch/platform/wayland_backends/kde.py`.

Будущие backend-файлы:

- `lswitch/platform/wayland_backends/gnome.py`;
- `lswitch/platform/wayland_backends/sway.py`;
- `lswitch/platform/wayland_backends/hyprland.py`.

## 6. Компоненты

### 6.1. `VirtualKeyboard.send_combo()`

Добавить метод в `lswitch/input/virtual_keyboard.py`.

Назначение:

- заменить `xdotool key`;
- отправлять сочетания вроде `ctrl+v`, `ctrl+shift+Left`, `alt+shift`;
- использовать тот же `UInput`, который уже нужен LSwitch.

Требования:

- принимать строку или список клавиш;
- иметь маппинг имен клавиш в evdev keycodes;
- нажимать модификаторы слева направо;
- нажимать и отпускать основную клавишу;
- отпускать модификаторы в обратном порядке;
- не падать, если `_uinput is None`, но логировать проблему в debug.

Первый набор имен:

- `ctrl`, `shift`, `alt`, `super`;
- `v`, `c`, `a`;
- `Left`, `Right`, `BackSpace`, `Return`, `Escape`.

### 6.2. `WaylandSystemAdapter`

Реализует `ISystemAdapter`.

Методы:

- `run_command()` остается subprocess-оберткой;
- `xdotool_key(sequence)` делегирует в `virtual_kb.send_combo(sequence)`;
- `get_clipboard()` и `set_clipboard()` получают Wayland-реализацию.

Для clipboard возможны два пути:

- Qt `QClipboard`, если запущен GUI и есть Qt event loop;
- `wl-copy`/`wl-paste` как fallback для headless.

Важно: `QClipboard.Selection` нельзя заранее считать гарантированно рабочим на Wayland. Нужно runtime-проверять `supportsSelection()` и фактическое поведение в KDE Plasma.

### 6.3. `WaylandSelectionAdapter`

Реализует `ISelectionAdapter`.

MVP-подход:

- если PRIMARY selection доступен, использовать его;
- если недоступен, отключить selection-mode и использовать retype fallback;
- `replace_selection()` делает set clipboard и `send_combo("ctrl+v")`;
- `expand_selection_to_word()` делает `send_combo("ctrl+shift+Left")`.

Риск:

- Wayland security model и поведение приложений могут отличаться;
- одинаковое поведение во всех приложениях не гарантируется;
- selection-mode должен быть опциональным, а не блокером MVP.

### 6.4. KDE layout backend

Добавить `lswitch/platform/wayland_backends/kde.py`.

Назначение:

- получить список раскладок;
- получить текущую раскладку;
- переключить раскладку.

План реализации:

1. Сначала сделать spike через `gdbus`/`busctl` introspection в реальной KDE Plasma Wayland-сессии.
2. Зафиксировать фактический D-Bus service/path/interface/methods.
3. Реализовать backend.
4. Добавить tests с mock-объектом D-Bus клиента.

Предполагаемый API требует проверки:

- service: `org.kde.keyboard`;
- object path: `/Layouts`;
- interface: `org.kde.KeyboardLayouts`;
- методы могут включать `getLayout`, `getLayoutsList`, `setLayout`.

Эти имена нельзя считать окончательными до introspection на целевой версии Plasma.

### 6.5. `libxkbcommon` для `keycode_to_char()`

Текущий X11-код использует `XkbKeycodeToKeysym`.

Для Wayland нужен отдельный слой через `libxkbcommon`.

Назначение:

- evdev keycode -> XKB keycode;
- XKB keycode + layout group + shift state -> keysym;
- keysym -> unicode char.

Важный пункт для проверки:

- в X11 сейчас используется `keycode + 8`;
- для `libxkbcommon` нужно отдельно подтвердить правильное смещение и mapping на реальной клавиатуре.

`libxkbcommon` не заменяет `maps.py`.

- `libxkbcommon`: keycode -> char;
- `maps.py`: char -> char для EN/RU конвертации.

Оба слоя нужны.

## 7. Изменения в `app.py`

Текущий `_init_platform()` жестко создает X11-адаптеры.

Нужно:

- создать `VirtualKeyboard` до выбора Wayland system adapter;
- вызвать `PlatformFactory`;
- получить `system`, `xkb`, `selection`;
- дальше оставить общий код создания `DictionaryService`, `AutoDetector`, `ConversionEngine`, `EventManager`, `DeviceManager`.

Также нужно:

- в `run()` заменить X11-only сообщение про `DISPLAY`;
- учитывать `WAYLAND_DISPLAY`;
- `_SelectionLoggerThread` оставлять только для X11 или только для адаптеров, которым нужен polling;
- для Wayland selection использовать встроенный механизм адаптера или fallback.

## 8. Установка и зависимости

Обновить:

- `scripts/install.sh`;
- `scripts/build-deb.sh`;
- `requirements.txt`;
- `setup.py`;
- `README.md`;
- `config/lswitch.service`;
- `config/config.json.example`, если появятся новые настройки.

Новые системные зависимости для Wayland MVP:

- `libxkbcommon`;
- Python bindings не обязательны, можно через `ctypes`;
- `wl-clipboard` как fallback для headless clipboard;
- D-Bus tools только для диагностики/spike, не как обязательная runtime-зависимость.

Вопрос по Qt:

- переходить ли полностью на PyQt6;
- или оставить PyQt5 GUI и сделать Wayland MVP без QtDBus.

Текущий исследовательский документ предлагает PyQt6-first. Это выглядит перспективно, но должно быть отдельным решением, потому что миграция UI на PyQt6 увеличивает объем работ.

## 9. План работ

### Фаза 0. Spike на реальной KDE Plasma Wayland

Задачи:

- проверить `XDG_SESSION_TYPE=wayland`;
- проверить `WAYLAND_DISPLAY`;
- проверить D-Bus introspection для KDE keyboard layouts;
- проверить, переключается ли раскладка через найденный D-Bus API;
- проверить `uinput` ввод в Konsole, Kate, Firefox, VS Code;
- проверить clipboard/selection:
  - обычный clipboard;
  - PRIMARY selection;
  - `QClipboard.supportsSelection()`;
  - `wl-paste --primary`;
- проверить задержки и race conditions при paste.

Результат:

- короткий протокол проверки;
- окончательное решение по KDE D-Bus API;
- решение по selection-mode в MVP.

### Фаза 1. PlatformFactory

Задачи:

- добавить `platform_factory.py`;
- реализовать `detect_session_type()`;
- реализовать `detect_compositor()`;
- добавить unit-тесты;
- интегрировать в `_init_platform()` без изменения поведения X11.

Критерий готовности:

- X11-тесты проходят;
- в Wayland-сессии приложение выбирает Wayland-ветку.

### Фаза 2. UInput combo API

Задачи:

- добавить `VirtualKeyboard.send_combo()`;
- добавить key name -> evdev keycode map;
- покрыть mock-тестами;
- заменить Wayland-использование `xdotool_key()` на `send_combo()`.

Критерий готовности:

- `ctrl+v` и `ctrl+shift+Left` отправляются через mock UInput в правильном порядке.

### Фаза 3. KDE layout backend

Задачи:

- добавить интерфейс `ILayoutBackend`;
- добавить KDE backend;
- добавить `WaylandXKBAdapter` как dispatcher;
- реализовать `get_layouts()`, `get_current_layout()`, `switch_layout()`;
- добавить тесты с mock D-Bus клиентом.

Критерий готовности:

- в KDE Plasma Wayland можно получить текущую раскладку и переключить ее.

### Фаза 4. `libxkbcommon` mapping

Задачи:

- добавить `xkbcommon_adapter.py`;
- реализовать keymap для текущих layouts;
- реализовать `keycode_to_char()`;
- проверить EN/RU на реальной клавиатуре;
- добавить тесты на уровне mock/табличных сценариев.

Критерий готовности:

- `_extract_last_word_events()` получает корректные символы в Wayland.

### Фаза 5. WaylandSystemAdapter и selection fallback

Задачи:

- добавить `WaylandSystemAdapter`;
- добавить clipboard путь;
- добавить `WaylandSelectionAdapter`;
- реализовать graceful degradation для недоступного PRIMARY selection;
- не блокировать retype-режим из-за selection.

Критерий готовности:

- retype работает в KDE Wayland;
- selection либо работает, либо явно отключен с понятным сообщением.

### Фаза 6. Интеграция приложения

Задачи:

- включить Wayland-ветку в `app.py`;
- обновить сообщения ошибок;
- обновить lifecycle selection logger;
- добавить debug logging выбранной платформы;
- проверить GUI/headless режимы.

Критерий готовности:

- `lswitch --debug` показывает выбранную платформу и backend;
- double Shift работает в KDE Wayland.

### Фаза 7. Установка, документация, упаковка

Задачи:

- обновить `scripts/install.sh`;
- обновить `scripts/build-deb.sh`;
- обновить README;
- добавить раздел troubleshooting для Wayland;
- описать поддержку KDE как MVP;
- описать ограничения GNOME/Sway/Hyprland.

Критерий готовности:

- установка сообщает нужные зависимости;
- документация не обещает больше, чем реализовано.

### Фаза 8. Follow-up: другие compositors

После KDE MVP:

- GNOME backend через `Gio.Settings` / D-Bus;
- Sway backend через IPC;
- Hyprland backend через socket IPC;
- CI/headless Wayland;
- исследование portals/libei для будущей более правильной модели input emulation.

## 10. Критерии приемки MVP

- `lswitch` запускается в KDE Plasma Wayland.
- `lswitch` не требует `DISPLAY`, если есть `WAYLAND_DISPLAY`.
- Double Shift конвертирует последнее слово в retype-режиме.
- После конвертации раскладка переключается корректно.
- X11-сценарии не регрессируют.
- Если selection-mode недоступен, приложение не падает.
- Пользователь получает понятное сообщение о неподдержанном compositor или режиме.
- Unit-тесты проходят.
- Ручная проверка выполнена минимум в Konsole, Kate, Firefox и VS Code.

## 11. Риски

| Риск | Вероятность | Влияние | Что делать |
|---|---:|---:|---|
| KDE D-Bus API отличается между версиями Plasma | Средняя | Высокое | Начать со spike и introspection |
| PRIMARY selection в Wayland работает не так, как в X11 | Высокая | Среднее | Selection не делать блокером MVP |
| `libxkbcommon` keycode offset отличается от ожиданий | Средняя | Высокое | Отдельный ручной тест keycode->char |
| PyQt6 migration увеличит объем работ | Средняя | Среднее | Решить отдельно: PyQt6-first или минимальный backend без миграции |
| Headless Wayland clipboard сложен без GUI event loop | Средняя | Среднее | `wl-clipboard` fallback |
| Wayland security model ограничит синтетический ввод | Низкая/средняя | Высокое | Продолжить использовать `uinput`, исследовать libei/portals как future |

## 12. Открытые вопросы

- Делаем ли полный переход PyQt5 -> PyQt6 в рамках Wayland MVP?
- Должен ли headless-режим поддерживать Wayland clipboard в MVP?
- Selection-mode в Wayland: поддерживаем сразу или оставляем experimental?
- Нужна ли настройка `preferred_platform_backend` в конфиге?
- Нужен ли CLI debug command для диагностики Wayland backend?
- Какие версии KDE Plasma считаем целевыми: Plasma 5, Plasma 6 или только Plasma 6?

## 13. Источники для проверки

- Qt `QClipboard`: https://doc.qt.io/qt-6/qclipboard.html
- libxkbcommon state API: https://xkbcommon.org/doc/current/group__state.html
- XDG Remote Desktop portal: https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html
- libei: https://libinput.pages.freedesktop.org/libei/
- KDE keyboard layouts user docs: https://docs.kde.org/stable5/en/plasma-desktop/kcontrol/keyboard/layouts.html

