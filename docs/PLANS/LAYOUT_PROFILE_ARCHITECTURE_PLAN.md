# Layout profile architecture plan

Дата: 2026-07-07

Этот файл фиксирует идею для дальнейшей проработки: отделить слой раскладок,
языков и пар конвертации от текущей EN/RU-специфичной логики, чтобы LSwitch мог
работать не только с `us <-> ru`, но и с другими парами раскладок.

## 1. Текущее состояние

Сейчас часть runtime уже работает на уровне физических key events:

- `RetypeMode` удаляет введенные символы, переключает раскладку и replay-ит
  сохраненные evdev keycodes;
- `IXKBAdapter` возвращает список layout-ов, текущий layout и умеет переключать
  layout;
- X11 backend частично умеет получать символ для `keycode + layout + shift`
  через XKB;
- Wayland backend пока содержит MVP-логику для US/RU.

Но продуктовая логика почти везде предполагает только два языка:

- `EN_TO_RU` / `RU_TO_EN` захардкожены в `lswitch/intelligence/maps.py`;
- `convert_text()` знает только направления `en_to_ru` и `ru_to_en`;
- язык определяется правилом "есть кириллица -> ru, иначе en";
- `AutoDetector` использует только EN/RU словари и EN/RU n-граммы;
- `_layout_to_lang()` возвращает только `en` или `ru`;
- auto-conversion на `Space` выбирает только `en_to_ru` или `ru_to_en`;
- `SelectionMode._find_layout_for_lang()` специально ищет `en/us` и `ru`;
- user dictionary хранит решения по ключам `convert.en`, `keep.ru`;
- прямой набор текста через `VirtualKeyboard` умеет EN и RU через обратную
  карту `RU_TO_EN`.

Вывод: текущая ручная retype-конвертация может случайно работать для другой
пары, если у пользователя ровно две раскладки и достаточно переключить на
следующую. Но auto-conversion, selection conversion, словари, обучение и прямой
typing сейчас EN/RU-specific.

## 2. Цель

Сделать слой раскладок таким, чтобы LSwitch описывал не "en/ru вообще", а
конкретные профили:

- какая XKB раскладка сейчас активна;
- какой язык связан с этой раскладкой;
- как физические клавиши отображаются в символы;
- какая пара раскладок разрешена для конвертации;
- какие словари, n-граммы и user-dict правила относятся к этой паре.

Идеальная цель:

```text
us <-> ru
us <-> de
us <-> uk
de <-> ru
...
```

без ручного добавления отдельных `EN_TO_DE`, `DE_TO_RU`, `UK_TO_EN` map-ов.

## 3. Базовые сущности

Предлагаемые модели:

```text
LayoutProfile
  id: "us", "ru", "de", "fr"
  xkb_name: "us", "ru", "de"
  display_name: "English (US)"
  index: XKB group index
  keymap: (keycode, level) -> char

LanguageProfile
  id: "en", "ru", "de"
  scripts: ["latin"], ["cyrillic"]
  dictionary
  ngram_model
  prefix_dictionary

ConversionPair
  id: "en_ru"
  source_layout_id: "us"
  source_lang_id: "en"
  target_layout_id: "ru"
  target_lang_id: "ru"
```

В runtime лучше работать с `ConversionPair`, а не с direction string вида
`en_to_ru`.

## 4. Авто-построение conversion map из XKB

Главная идея: карту конвертации нужно строить из XKB keymap-ов, а не хранить
как Python dict для каждой пары языков.

Пример:

```text
keycode 34:
  us level 0 -> g
  ru level 0 -> п

derived map us->ru:
  g -> п
```

Для каждой пары layout-ов можно построить:

```text
char_map[source_char] = target_char
reverse_char_map[target_char] = source_char
```

Это автоматически масштабируется на другие пары, пока обе раскладки доступны в
XKB и backend умеет читать `keycode + layout group + shift level`.

Нужно учитывать уровни:

- level 0: обычная клавиша;
- level 1: Shift;
- в будущем level 2/3: AltGr, dead keys, compose sequences.

Для MVP достаточно level 0/1 и printable single-character keysyms.

## 5. Конфигурация

Возможная структура конфига:

```toml
[layout_profiles.us]
xkb_name = "us"
language = "en"

[layout_profiles.ru]
xkb_name = "ru"
language = "ru"

[[layout_pairs]]
id = "en_ru"
source_layout = "us"
target_layout = "ru"
source_language = "en"
target_language = "ru"
enabled = true

[layout_runtime]
active_pair = "en_ru"
```

Для простого сценария можно автоматически создать pair из первых двух активных
XKB раскладок. Но как только у пользователя `us/ru/de`, простое
`switch_layout()` "на следующую" становится неправильным: нужно всегда
переключаться в конкретный target layout по `LayoutInfo.index`.

## 6. User dictionary

Текущий формат:

```toml
[convert.en]
"ghbdtn" = 2

[keep.ru]
"привет" = 2
```

Проблема: `en` как source language недостаточно, потому что один и тот же текст
может иметь разные решения в разных target pairs.

Предлагаемый формат для будущей версии:

```toml
[pairs.en_ru.convert.us]
"ghbdtn" = 2

[pairs.en_ru.keep.us]
"hello" = 2

[pairs.en_de.convert.us]
"..." = 2
```

Минимальная миграционная стратегия:

- старые `[convert.en]` / `[keep.ru]` читать как legacy;
- если active pair `en_ru`, применять legacy правила к этой паре;
- новые записи писать уже в pair-scoped формат.

## 7. AutoDetector и словари

Текущий `AutoDetector` должен быть разделен на:

```text
LayoutConverter
  - convert_text(text, pair, direction)
  - convert_key_events(events, source_layout, target_layout)

LanguageEvidence
  - dictionary lookup
  - ngram score
  - prefix score

PairAutoDetector
  - принимает word + current LayoutProfile
  - выбирает ConversionPair
  - сравнивает source/target language evidence
```

Словари и n-граммы должны быть зарегистрированы по `language_id`, а не быть
захардкожены в `if lang == "ru" else en`.

Для языков без встроенных моделей:

- dictionary-based detection может работать, если есть системный Hunspell;
- n-gram fallback можно отключить или заменить более слабой эвристикой;
- auto-conversion для пары можно считать unavailable, но ручной retype оставить.

## 8. Selection conversion

Selection conversion сейчас использует `invert_layout_runs()`, который делит
текст на Latin/Cyrillic runs и конвертирует EN/RU.

В идеале selection conversion должен:

- определять source layout/language для каждого run;
- выбирать target layout через active pair;
- конвертировать run через derived char map;
- для mixed text сохранять punctuation/whitespace как neutral;
- если run не принадлежит ни одной known language/script, оставлять как есть.

Для первой итерации можно оставить selection conversion EN/RU-only и расширять
после появления `LayoutProfile`.

## 9. Virtual keyboard direct typing

Сейчас прямой набор символов делает EN key lookup, а для RU использует
`RU_TO_EN`, чтобы найти физическую клавишу.

В идеальной модели нужен API:

```text
LayoutProfile.char_to_key(ch) -> (keycode, shift/level)
LayoutProfile.key_to_char(keycode, level) -> ch
```

Тогда прямой набор текста будет работать для любой раскладки, для которой
построен reverse keymap.

Ограничения MVP:

- single-character printable symbols;
- без compose/dead keys;
- без AltGr;
- если символ нельзя набрать в target layout, direct typing должен fail-fast и
  выбрать clipboard/paste fallback, где он доступен.

## 10. Platform requirements

X11:

- использовать XKB group index из `LayoutInfo.index`;
- читать printable keysyms для keycode + group + level;
- строить keymap на startup и обновлять при изменении layout list.

Wayland:

- compositor-specific backend должен вернуть список layout-ов и текущий index;
- для KDE/Plasma можно получать layout state через D-Bus;
- keymap для `keycode -> char` лучше строить через libxkbcommon или надежный
  backend, а не через hardcoded US/RU map;
- текущий Wayland MVP с `EN_TO_RU` оставить как fallback до полноценной keymap
  реализации.

## 11. Миграционный план

1. Добавить `LayoutProfile`, `LanguageProfile`, `ConversionPair` как новые
   модели без изменения поведения.
2. Добавить `LayoutRegistry`, который из текущих XKB layout-ов строит profiles.
3. Добавить builder для derived char map между двумя layout profiles.
4. Переписать `convert_text()` на pair-aware API, оставив старую EN/RU функцию
   как compatibility wrapper.
5. Переписать `_layout_to_lang()` на lookup через registry.
6. Переписать auto-conversion на active `ConversionPair`.
7. Переписать `SelectionMode._find_layout_for_lang()` на target layout lookup.
8. Ввести pair-scoped user dictionary и legacy migration.
9. Расширить tests: `us<->ru`, `us<->de`, multi-layout `us/ru/de`, missing
   dictionary, unknown layout.
10. После стабилизации удалить прямые зависимости от `EN_TO_RU` из app/core.

## 12. Главный принцип

Core-логика не должна знать, что такое `ru` как особый случай. Она должна знать:

- текущий layout profile;
- target layout profile;
- active conversion pair;
- language evidence для source/target языков;
- keymap, построенный из platform/XKB.

EN/RU должны стать дефолтным preset-ом, а не архитектурным ограничением.
