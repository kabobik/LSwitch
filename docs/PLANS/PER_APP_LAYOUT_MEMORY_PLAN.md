# Per-app layout memory plan

Дата: 2026-07-07

Этот файл фиксирует идею для дальнейшей проработки: запоминать раскладку по
приложению или окну, чтобы при смене фокуса LSwitch автоматически восстанавливал
последнюю раскладку для текущего приложения.

MVP целевой платформы: **KDE Plasma Wayland**.

## 1. Цель

Сценарий:

- пользователь пишет в терминале на EN;
- переключается в мессенджер, где последняя раскладка была RU;
- LSwitch видит смену активного приложения и восстанавливает RU;
- пользователь возвращается в терминал, LSwitch восстанавливает EN.

Это должно работать независимо от auto-conversion. Фича отвечает не за
исправление уже набранного текста, а за выбор правильной раскладки до следующего
ввода.

## 2. Реалистичность на Wayland

На Wayland нет единого безопасного API, который любой процесс может использовать
для глобального чтения активного окна. Это часть privacy/security модели
Wayland.

Поэтому feature должна быть compositor-specific:

- KDE Plasma Wayland - реально, лучший MVP target;
- Sway/wlroots - реально через IPC;
- Hyprland - реально через socket/hyprctl events;
- GNOME Wayland - сложнее, вероятно нужен GNOME Shell extension;
- generic Wayland backend - не обещать.

В текущей архитектуре это нормально ложится в `platform_factory`: добавить
optional capability `active_app_provider`, как уже сделано для layout backend,
selection backend и system adapter.

## 3. Почему MVP именно KDE Wayland

Причины:

- KDE Wayland уже является первым целевым compositor-ом проекта;
- в коде уже есть `KdeLayoutBackend` через `org.kde.KeyboardLayouts`;
- layout switching и current layout на KDE уже вынесены в backend;
- можно развивать новую feature рядом с существующим KDE D-Bus/Qt bridge;
- пользовательский сценарий можно проверить на одной основной платформе до
  расширения на Sway/Hyprland/GNOME.

Открытый вопрос для KDE: надежный источник active window/app identity.
Возможные варианты:

- KWin scripting;
- KWin/Plasma D-Bus API, если доступен и стабилен;
- helper KWin script, который публикует focus change events в LSwitch;
- fallback polling, если событийная модель недоступна.

## 4. Предлагаемая архитектура

```text
ActiveAppProvider
  current_app() -> AppIdentity | None
  subscribe_focus_changed(callback)

LayoutMemoryStore
  get(app_key) -> remembered_layout_id | None
  set(app_key, layout_id)
  flush()

LayoutMemoryController
  on_focus_lost(previous_app):
    save current layout for previous app

  on_focus_gained(new_app):
    restore remembered layout for new app

  on_layout_changed(layout):
    update memory for current app
```

`ActiveAppProvider` должен быть platform-specific. Core/controller не должен
знать, KDE это, Sway или Hyprland.

## 5. App identity

Нельзя использовать только window title: он слишком шумный и часто меняется.

Предлагаемая модель:

```text
AppIdentity
  compositor: "kde"
  app_id: "org.kde.konsole" | None
  window_class: "konsole" | None
  window_role: optional
  pid: optional
  title: optional diagnostic only
```

Ключ памяти по умолчанию:

```text
app_id || window_class || pid fallback
```

Title использовать только для diagnostics или будущего advanced mode. Для
браузеров, IDE и терминалов title-based memory почти наверняка будет слишком
нестабильной.

## 6. Хранилище

Отдельный файл, не смешивать с `config.toml`:

```text
~/.config/lswitch/layout_memory.toml
```

Возможный формат:

```toml
[apps."org.kde.konsole"]
layout = "us"
layout_index = 0
updated_at = 1783450000

[apps."org.telegram.desktop"]
layout = "ru"
layout_index = 1
updated_at = 1783450100
```

Хранить лучше и layout id/xkb name, и индекс. Приоритет при восстановлении:

1. найти layout по стабильному id/xkb name;
2. если не найден, использовать index только если он валиден;
3. если ничего не найдено, не переключать.

## 7. Конфиг

Предлагаемые настройки:

```toml
# Remember and restore keyboard layout per active application.
per_app_layout_memory = false

# Backend selection. "auto" means platform default.
per_app_layout_backend = "auto"

# Memory granularity: app, window, title.
per_app_layout_scope = "app"

# Delay before restoring layout after focus change, seconds.
per_app_layout_restore_delay = 0.08
```

По умолчанию выключить. Это фича, которая может конфликтовать с настройками
desktop environment.

## 8. KDE Wayland MVP flow

Минимальный flow:

```text
startup:
  provider = KdeActiveAppProvider(...)
  controller = LayoutMemoryController(provider, xkb, store)
  current_app = provider.current_app()
  current_layout = xkb.get_current_layout()
  store.set(current_app, current_layout)

focus changed:
  previous_app = controller.current_app
  previous_layout = xkb.get_current_layout()
  store.set(previous_app, previous_layout)

  new_app = provider.current_app()
  remembered = store.get(new_app)
  if remembered exists:
    xkb.switch_layout(target=remembered)
```

Нужен небольшой debounce 50-150 ms:

- focus events могут приходить пачкой;
- layout state может обновиться чуть позже;
- не надо переключать layout во время transient focus states.

## 9. Взаимодействие с LSwitch auto-conversion

LSwitch сам может менять раскладку:

- manual `Shift+Shift`;
- auto-conversion on `Space`;
- future mid-word switch;
- selection conversion.

Все эти изменения должны считаться изменением раскладки активного приложения.
Иначе controller восстановит старое значение и сломает поведение.

Правило:

- после успешного `xkb.switch_layout(...)` layout memory для текущего app нужно
  обновить;
- если переключение было временным или откатилось из-за ошибки, memory не менять;
- если active app неизвестен, memory не писать.

## 10. Конфликты с desktop environment

KDE/GNOME могут иметь собственные настройки раскладки:

- global layout;
- per-window layout;
- per-application layout.

Если DE уже делает per-app/per-window layout memory, LSwitch может начать
бороться с compositor-ом. Для MVP:

- feature выключена по умолчанию;
- diagnostics должны показывать предупреждение, если возможно обнаружить
  конфликтующую настройку;
- документация должна рекомендовать включать только один механизм памяти
  раскладки.

## 11. Backend-и после KDE

Sway:

- использовать sway IPC;
- подписаться на `window` focus events;
- `get_tree` для текущего focused container;
- app identity: `app_id` для Wayland, `window_properties.class` для XWayland.

Hyprland:

- использовать socket events или `hyprctl activewindow -j`;
- app identity: `class`, `initialClass`, `pid`, `title` diagnostic.

GNOME Wayland:

- вероятно нужен GNOME Shell extension;
- extension должен отдавать active app/window events в LSwitch;
- без extension feature лучше считать unsupported.

Generic Wayland:

- не обещать active app discovery;
- graceful unavailable state.

## 12. Diagnostics

Добавить read-only diagnostics:

```text
per-app layout memory:
  enabled: false
  backend: kde
  active app: org.kde.konsole
  current layout: us
  remembered layout: us
  store path: ~/.config/lswitch/layout_memory.toml
  focus events: available/unavailable
```

Для KDE отдельно:

- найден ли KWin active app provider;
- установлен ли helper KWin script, если он нужен;
- можно ли получить current active app;
- можно ли получить focus changed events.

## 13. Технические риски

- Wayland privacy model не дает универсального active window API.
- Active app может быть неизвестен для XWayland, Flatpak, Electron или sandboxed
  приложений.
- Focus change может прийти позже первого keypress.
- Layout restore может конфликтовать с системными shortcuts и настройками DE.
- Нужно аккуратно обрабатывать suspend/resume, screen lock, modal dialogs и
  transient windows.
- Нельзя часто писать TOML на диск при каждом keypress; store должен flush-ить
  умеренно.

## 14. MVP-план

1. Добавить интерфейс `ActiveAppProvider`.
2. Добавить `LayoutMemoryStore` с TOML persistence.
3. Добавить `LayoutMemoryController` без platform-specific кода.
4. Добавить config keys, default disabled.
5. Реализовать KDE Wayland active app backend.
6. Подключить backend через `platform_factory`.
7. Обновлять memory после успешных layout switches внутри LSwitch.
8. Добавить diagnostics.
9. Добавить manual QA для KDE Wayland:
   - Konsole EN;
   - Telegram RU;
   - browser EN;
   - focus switching;
   - manual layout changes;
   - auto-conversion layout changes.

MVP считается успешным, если на KDE Wayland LSwitch стабильно запоминает
раскладку по app id и восстанавливает ее до следующего ввода после смены фокуса.
