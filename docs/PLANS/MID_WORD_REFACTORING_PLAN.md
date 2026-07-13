# Mid-word pre-refactoring plan

Дата: 2026-07-07

> Архивный подготовительный план. Итоговая реализация использует единый
> `auto_switch`; актуальные решения находятся в
> `docs/PLANS/WORD_PROCESSING_PIPELINE_PLAN.md`.

Этот файл фиксирует подготовительный план перед реализацией
`docs/MID_WORD_SYSTEM_DICTIONARY_PLAN.md`. Цель - сначала убрать хрупкие места в
буфере ввода, replay/undo и конфиге, чтобы mid-word режим добавлялся как
отдельная feature, а не как новый набор условий внутри `LSwitchApp`.

## 1. Почему нужен отдельный рефакторинг

Mid-word режим будет срабатывать в самом горячем месте приложения: на каждом
обычном символе в `_on_key_press()`. Сейчас там уже смешаны несколько
ответственностей:

- обновление state machine;
- обслуживание `event_buffer` и `chars_in_buffer`;
- обработка `Backspace`, `Space`, modifiers и selection flags;
- запуск auto-conversion на `Space`;
- сброс sticky/repeat state.

Дополнительно auto-conversion и manual undo сейчас используют частично
дублирующиеся операции:

- извлечь последнее слово из `event_buffer`;
- удалить введенные символы через `Backspace`;
- переключить раскладку;
- replay-ить сохраненные key events;
- сохранить marker для Shift+Shift undo;
- сбросить context.

Если добавить mid-word поверх текущего вида, новый режим будет зависеть от
тонких деталей `_last_auto_marker`, `_pending_auto_space`,
`_last_retype_events`, selection flags и `chars_in_buffer`. Сначала нужно
выделить эти операции в явные маленькие компоненты.

## 2. Цель подготовки

После рефакторинга должно быть возможно реализовать mid-word flow так:

```text
KeyPress(letter)
  -> TypedBuffer.append()
  -> current token extraction
  -> MidWordDetector decision
  -> RetypeService.retype(events, target_layout, delete_count)
  -> AutoConversionMarker(kind="mid_word")
```

без копирования логики из auto-conversion на `Space` и без новых крупных блоков
в `LSwitchApp._on_key_press()`.

## 3. Не цели

В рамках подготовительного рефакторинга не нужно:

- реализовывать `MidWordDetector`;
- читать системные Hunspell словари;
- менять алгоритм текущего `AutoDetector`;
- расширять поддержку языков за пределы текущей пары EN/RU;
- менять пользовательское поведение auto-conversion на `Space`.

Результат подготовки должен быть поведенчески совместимым с текущими тестами.

## 4. Этап 1 - Typed buffer service

Добавить компонент, который владеет операциями над текущим typed buffer.

Возможный модуль:

```text
lswitch/core/typed_buffer.py
```

Возможные сущности:

```text
TypedToken
  text: str
  events: list[KeyEventData]
  start_offset: int
  end_offset: int
  has_trailing_space: bool
  eligible_for_auto: bool
  reject_reason: str

TypedBufferService
  append_key(context, key_event, shifted)
  backspace(context)
  backspace_repeat(context)
  reset(context)
  decode(events, layout=None)
  last_word(context, layout=None) -> TypedToken
  current_token(context, layout=None) -> TypedToken
```

Минимально на этом этапе можно не переносить весь state machine. Достаточно
вынести:

- добавление обычной клавиши в `event_buffer`;
- добавление `Space`;
- удаление последнего события на `Backspace`;
- извлечение последнего слова;
- decode buffer для debug log.

Важно сохранить текущую особенность `_extract_last_word_events()`: для
space-triggered auto-conversion она не должна ломать русские буквы, которые на
EN physical map выглядят как punctuation keys.

Отдельно для будущего mid-word добавить более строгий token classifier, но пока
не подключать его к поведению:

```text
is_mid_word_candidate(token)
  - только буквы;
  - без digits;
  - без punctuation;
  - без whitespace;
  - без URL/email/path-like признаков;
  - без all-caps/CamelCase, если политика это запрещает.
```

### Acceptance

- Все текущие тесты auto-conversion проходят без изменения ожидаемого
  поведения.
- Тесты на `_extract_last_word_events()` перенесены или дополнены тестами
  `TypedBufferService.last_word()`.
- `LSwitchApp._on_key_press()` становится короче: добавление/удаление событий
  выполняется через сервис.

## 5. Этап 2 - Retype/replay primitive

Сейчас похожая логика есть в двух местах:

- `RetypeMode.execute()` - ручная retype conversion;
- `LSwitchApp._do_auto_conversion_at_space()` - auto-conversion на `Space`.

Нужно вынести общий низкоуровневый primitive:

```text
RetypeService
  retype_events(
    events,
    delete_count,
    target_layout=None,
    switch_to_next=False,
    before_replay_delay=...,
  ) -> bool
```

Правила:

- `target_layout` используется для auto-conversion и будущего mid-word;
- `switch_to_next=True` сохраняет поведение ручной retype conversion;
- replay всегда работает по исходным physical key events;
- сервис не знает про словари, detector-ы, selection и user dictionary.

`RetypeMode` должен стать тонкой оберткой над `RetypeService`.
`_do_auto_conversion_at_space()` тоже должен использовать этот сервис.

### Acceptance

- Тесты `tests/test_retype_mode.py` и `tests/test_auto_convert.py` проходят.
- Поведение deferred Space после auto-conversion остается в `LSwitchApp`, потому
  что это policy вокруг физического `Space`, а не обязанность replay primitive.
- В коде остается одно место, которое делает `tap_key(KEY_BACKSPACE)` +
  `switch_layout()` + `replay_events()` для typed events.

## 6. Этап 3 - Unified auto-conversion marker

Заменить dict-based `_last_auto_marker` на явную dataclass-модель.

Возможный модуль:

```text
lswitch/core/auto_marker.py
```

Возможная модель:

```text
AutoConversionMarker
  kind: "space" | "mid_word"
  original_word: str
  original_lang: str
  target_lang: str
  direction: str
  word_events: list[KeyEventData]
  converted_len: int
  had_space: bool
  created_at: float
```

Для текущего поведения нужен только `kind="space"`, но модель должна сразу
учитывать будущий `kind="mid_word"`.

Undo flow должен принимать marker и выполнять:

- user-dict correction для исходного слова;
- удаление результата;
- переключение на исходную раскладку;
- replay исходных events;
- восстановление пробела только если `had_space=True`.

### Acceptance

- Shift+Shift undo после auto-conversion на `Space` работает как раньше.
- Тесты undo больше не зависят от magic dict keys.
- Marker очищается на navigation/mouse click так же, как сейчас.

## 7. Этап 4 - Layout/lang helpers

Сейчас `_layout_to_lang()` живет в `LSwitchApp` и знает только EN/RU. Перед
mid-word достаточно минимального выноса, без полноценной layout profile
архитектуры.

Возможный модуль:

```text
lswitch/core/layout_helpers.py
```

API:

```text
layout_to_lang(layout_info) -> "en" | "ru"
find_layout_for_lang(layouts, lang) -> LayoutInfo | None
opposite_lang(lang) -> "en" | "ru"
direction_for_source_lang(lang) -> "en_to_ru" | "ru_to_en"
```

После этого `SelectionMode._find_layout_for_lang()`,
`LSwitchApp._layout_to_lang()`, auto-conversion и future mid-word должны
переиспользовать одну реализацию.

### Acceptance

- Поведение для `en/us` и `ru` не меняется.
- Дублирование поиска target layout уменьшается.
- Тесты на layout helpers покрывают `en`, `us`, `ru`, unknown fallback.

## 8. Этап 5 - Config groundwork

Подготовить конфиг к будущим ключам, но не включать feature.

Добавить в `DEFAULT_CONFIG`:

```toml
auto_switch_mid_word = false
mid_word_min_prefix_len = 4
system_dict_enabled = true
system_dict_en_path = ""
system_dict_ru_path = ""
```

Обновить:

- validation в `validate_config()`;
- `_CONFIG_COMMENTS`;
- `config/config.toml.example`;
- README config section при необходимости;
- tests в `tests/test_config.py`.

На этом этапе ключи могут быть неиспользуемыми runtime-ом. Главное, чтобы
пользовательский config уже мог безопасно их хранить и мигрировать.

### Acceptance

- Config roundtrip сохраняет новые ключи.
- Invalid values отклоняются:
  - `auto_switch_mid_word` не bool;
  - `mid_word_min_prefix_len < 1`;
  - `system_dict_enabled` не bool;
  - explicit paths не строки.
- Feature остается выключенной по умолчанию.

## 9. Этап 6 - Prefix dictionary skeleton

Добавить чистый, не подключенный к runtime компонент:

```text
lswitch/intelligence/prefix_dictionary.py
```

API:

```text
PrefixDictionary.from_word_sets({"en": words, "ru": words})
in_lang(lang, word) -> bool
has_prefix(lang, prefix) -> bool
prefix_count(lang, prefix) -> int
word_count(lang) -> int
```

На этом этапе использовать встроенные `en_words.py` / `ru_words.py`. Системные
словари не подключать.

### Acceptance

- Unit tests покрывают:
  - full word lookup;
  - prefix lookup;
  - prefix counts;
  - case-insensitive lookup;
  - unknown language;
  - пустые строки.
- Runtime поведение LSwitch не меняется.

## 10. Этап 7 - Diagnostics groundwork

Добавить read-only helper для диагностики словарей, но без installer
requirements.

Возможный модуль:

```text
lswitch/intelligence/system_dictionary_loader.py
```

На подготовительном этапе можно реализовать только discovery:

```text
discover_hunspell_dictionaries(paths=None) -> list[DictionaryCandidate]
select_dictionary(lang, candidates, explicit_path="") -> DictionaryCandidate | None
```

Загрузка `.dic` может быть следующим этапом вместе с mid-word detector, но
diagnostics уже должны уметь показать, что на системе есть кандидаты.

### Acceptance

- Unit tests используют `tmp_path`, не зависят от реального `/usr/share`.
- Wayland diagnostics или отдельный diagnostic helper могут показать:
  - найден ли EN candidate;
  - найден ли RU candidate;
  - какой path выбран.

## 11. Рекомендуемый порядок PR/коммитов

1. `typed-buffer-service`
2. `retype-service`
3. `auto-conversion-marker`
4. `layout-lang-helpers`
5. `mid-word-config-keys`
6. `prefix-dictionary-skeleton`
7. `system-dictionary-discovery`

Каждый шаг должен быть поведенчески нейтральным, кроме добавления новых
неиспользуемых config keys. Это позволит остановиться после любого этапа без
полусломанного mid-word режима.

## 12. Готовность к старту mid-word реализации

Можно начинать `MidWordDetector` и runtime integration, когда выполнены условия:

- `LSwitchApp._on_key_press()` не содержит ручной логики append/pop для каждого
  обычного символа;
- есть единый replay primitive с explicit target layout;
- undo работает через typed marker object;
- новые config keys валидируются и сохраняются;
- `PrefixDictionary` покрыт unit tests;
- текущий набор тестов проходит.

После этого `docs/MID_WORD_SYSTEM_DICTIONARY_PLAN.md` можно уточнить: заменить
MVP-порядок на зависимость от этого pre-refactoring plan.
