# GUI settings manual testing

Дата актуализации: 2026-07-13

Документ проверяет окно `Настройки…`, live-применение `config.toml` и
синхронизацию tray. Unit/integration и offscreen Qt smoke tests выполняются в
CI/локальном test suite. Проверки реального ввода отмечаются отдельно для X11
и Wayland и требуют соответствующей пользовательской сессии.

## Статус

- Automated suite и offscreen создание окна: выполнено при реализации.
- Source installer scripts: синтаксическая проверка выполнена.
- Editable package metadata check: ожидает окружения с `setuptools`; в текущем
  окружении GUI import и offscreen smoke прошли, но `setup.py check` недоступен.
- X11 manual session: ожидает запуска в X11.
- KDE Plasma Wayland manual session: ожидает запуска в Wayland.

Наличие ожидающих platform-сессий не означает автоматизированный дефект: их
результаты нельзя достоверно получить из headless/offscreen окружения.

## Подготовка

1. Сохранить резервную копию `~/.config/lswitch/config.toml`.
2. Запустить приложение из рабочей копии:

   ```bash
   .venv/bin/python -m lswitch --replace
   ```

3. Записать PID из `${XDG_RUNTIME_DIR:-/run/user/$UID}/lswitch.pid`.
4. Открыть tray menu и выбрать `Настройки…`.
5. Убедиться, что окно содержит страницы `Основные`, `Автокоррекция`,
   `Словари`, `Выделение`, `Дополнительно`.

## Общий GUI и транзакция

1. Изменить параметры на двух страницах и нажать `Применить`.
   Ожидается: окно остаётся открытым, TOML обновлён, PID не изменился.
2. Изменить ещё одно значение и нажать `Отмена`.
   Ожидается: последнее изменение отсутствует в TOML и runtime.
3. Повторно выбрать `Настройки…` в tray.
   Ожидается: активируется то же окно, второй экземпляр не создаётся.
4. Проверить `Сбросить страницу` и `Сбросить всё` до `Применить`.
   Ожидается: меняется только draft; runtime и TOML остаются прежними.
5. Включить и выключить `Отладочное журналирование и монитор`.
   Ожидается: уровень логов и видимость `Debug Monitor` меняются без restart.
6. Запустить отдельно с `--trace`, выключить `debug` в GUI.
   Ожидается: GUI показывает пояснение, effective level остаётся `TRACE`.

## Зависимые параметры

При отключении parent значение child не должно сбрасываться. После повторного
включения parent должно отображаться прежнее значение.

| Действие | Ожидаемое визуальное состояние |
|---|---|
| Выключить `auto_switch` | Отключён `auto_switch_threshold` |
| Выключить `auto_switch_mid_word` | Отключены prefix length и system dictionaries |
| Выключить `system_dict_enabled` | Отключены оба пути `.dic` и кнопки обзора |
| Выключить `user_dict_enabled` | Отключены weight и auto-confirm |
| Оставить user dictionary, выключить auto-switch | Отключён только auto-confirm |
| Выбрать Wayland strategy `disabled` | Отключены все Wayland selection timings |
| Выбрать `primary_selection` | Доступен только expand delay из этой timing-группы |

## Ошибки без частичного применения

1. Указать несуществующий явный путь `system_dict_en_path` и применить.
   Ожидается: видна ошибка, окно открыто, TOML/runtime не изменились.
2. Указать каталог вместо `.dic` файла.
   Ожидается тот же транзакционный отказ.
3. Указать некорректную резервную комбинацию.
   Ожидается: ошибка до записи TOML.
4. Сделать каталог конфигурации временно недоступным для записи и применить
   безопасное изменение.
   Ожидается: старые memory/runtime/TOML остаются активными.

## Внешнее изменение и SIGHUP

1. Открыть чистое окно, изменить TOML внешним редактором и отправить:

   ```bash
   kill -HUP "$(cat "${XDG_RUNTIME_DIR:-/run/user/$UID}/lswitch.pid")"
   ```

   Ожидается: чистое окно и tray обновляются.
2. Повторить с несохранённым draft.
   Ожидается: пользовательские поля сохранены, показано уведомление; при
   `Применить` dirty paths объединяются с последним committed snapshot.
3. Записать невалидный TOML и отправить `SIGHUP`.
   Ожидается: ошибка в log, старый memory/runtime остаётся активным, внешний
   файл автоматически не перезаписывается.

## X11

1. Изменить `double_click_timeout` и проверить двойной Shift без restart.
2. Изменить `timing.key_press_delay` и `key_repeat_delay`; проверить retype.
3. Изменить `x11_selection_timing.poll_interval`; убедиться, что polling
   использует новый интервал без пересоздания процесса.
4. Изменить paste/restore/expand delays и проверить конвертацию выделения.
5. Проверить `switch_layout_after_convert=true/false` для typed text,
   selection, space auto, mid-word и undo.
6. Проверить canonical `Alt+Shift` и legacy `Alt_L+Shift_L` как fallback при
   недоступном прямом target switch.
7. При наличии трёх раскладок убедиться, что достигается точный target и цикл
   ограничен числом раскладок.

## KDE Plasma Wayland

Перед этим выполнить базовые проверки из
[`WAYLAND_MANUAL_TESTING.md`](WAYLAND_MANUAL_TESTING.md).

1. Перебрать `auto`, `clipboard_copy`, `primary_selection`, `disabled` и
   проверить selection conversion для каждой стратегии.
2. После смены стратегии убедиться, что старое clipboard/selection состояние
   не используется.
3. Изменить `wayland_timing.wl_clipboard_timeout` и все доступные
   `wayland_selection_timing.*`; проверить следующий conversion без restart.
4. Проверить layout policy `true/false` для прямого ввода и clipboard flow.
5. Проверить прямой KDE D-Bus target switch и верифицированный shortcut
   fallback при смоделированной ошибке backend-а.
6. Убедиться, что открытие Debug Monitor не создаёт idle `Ctrl+C` polling.

## Отчёт

Для каждой platform-сессии зафиксировать дату, DE, display server, commit,
успешные пункты и отклонения. При ошибке приложить 20–40 строк `--debug` или
`--trace` log вокруг события, не публикуя содержимое пользовательского ввода.
