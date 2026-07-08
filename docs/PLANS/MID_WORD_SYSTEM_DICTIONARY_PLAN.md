# Mid-word system dictionary plan

Дата: 2026-07-07

Этот файл фиксирует идею для дальнейшей проработки: использовать системные
орфографические словари, чтобы LSwitch мог определять неправильную раскладку
еще во время набора слова, а не только на пробеле.

## 1. Цель

Сейчас авто-конвертация работает на границе слова: пользователь нажал `Space`,
LSwitch извлек последнее слово из `event_buffer`, проверил его через
`AutoDetector`, удалил слово и пробел, переключил раскладку и воспроизвел
исходные key events.

Новая цель - отдельный opt-in режим:

- пользователь начинает печатать слово;
- после 3-4 символов LSwitch проверяет текущий префикс;
- если префикс почти невозможен в текущей раскладке, но после конвертации
  является нормальным началом слова в другой раскладке, LSwitch переключает
  раскладку до завершения слова;
- уже введенный префикс переигрывается в правильной раскладке, дальше пользователь
  продолжает набор без ожидания `Space`.

## 2. Почему нужен не просто словарь, а префиксный индекс

Текущий `DictionaryService` хранит встроенные словари как `set[str]` и умеет
быстро отвечать только на вопрос "есть ли полное слово". Для mid-word режима
нужно отвечать на другие вопросы:

- есть ли слова текущего языка с таким префиксом;
- есть ли слова целевого языка с конвертированным префиксом;
- насколько префикс неоднозначен;
- не является ли префикс слишком коротким для уверенного решения.

Пример EN layout:

```text
typed prefix:      ghb
converted prefix:  при

EN prefix "ghb":   редко/нет
RU prefix "при":   много слов
decision:          можно переключить EN -> RU
```

Без префиксного индекса придется сканировать весь словарь на каждый символ, что
не подходит для evdev hot path.

## 3. Предлагаемая архитектура

Добавить отдельные компоненты, не смешивая их с текущим `AutoDetector`:

```text
SystemDictionaryLoader
  - ищет Hunspell/MySpell словари в системных путях;
  - читает .dic файлы;
  - удаляет Hunspell-флаги после "/";
  - фильтрует слова по алфавиту и минимальной длине.

PrefixDictionary
  - хранит word set для полного слова;
  - хранит prefix set или prefix counts;
  - API:
      in_lang(lang, word) -> bool
      has_prefix(lang, prefix) -> bool
      prefix_count(lang, prefix) -> int

MidWordDetector
  - получает typed prefix и current_lang;
  - строит converted prefix;
  - проверяет source/target prefix evidence;
  - возвращает decision + reason.
```

Интеграция не должна добавляться напрямую в `LSwitchApp`. После модульного
рефакторинга входная точка должна быть такой:

```text
InputEventRouter / typing flow
  -> ConversionRuntimeFacade
    -> SpaceAutoConversionUseCase
    -> MidWordAutoConversionUseCase
      -> AutoConversionCandidate / prefix provider
      -> MidWordDetector
      -> RetypeService
      -> AutoConversionMarker(kind="mid_word")
```

Текущий space-triggered flow должен иметь явную точку расширения для candidate
extraction рядом с `SpaceAutoConversionUseCase`. Mid-word режим подключается
через новый use case, который переиспользует typed-buffer candidate/prefix
extraction, `RetypeService` и typed marker model.

## 4. Настройки

Предлагаемые настройки:

```toml
# Enable layout switching while a word is still being typed.
auto_switch_mid_word = false

# Minimum prefix length before mid-word detection starts.
mid_word_min_prefix_len = 4

# Use system Hunspell/MySpell dictionaries when available.
system_dict_enabled = true

# Optional explicit dictionary paths. Empty means auto-detect.
system_dict_en_path = ""
system_dict_ru_path = ""
```

По умолчанию `auto_switch_mid_word` должен быть выключен. Это более агрессивный
режим, чем auto-conversion на пробеле.

## 5. Политика уверенности

Минимальная безопасная политика для MVP:

- не проверять префиксы короче 4 символов;
- не переключать, если текущий префикс существует в текущем языке;
- переключать только если конвертированный префикс существует в целевом языке;
- игнорировать ввод с цифрами, пробелами, punctuation, URL/email/path-like текстом;
- игнорировать all-caps и смешанный CamelCase до отдельной проработки;
- не делать user-dict confirmation до завершения слова;
- `Shift+Shift` после mid-word switch должен уметь откатить последний mid-word
  switch и добавить защиту в user dictionary.

Более строгая политика после MVP:

- использовать `prefix_count` вместо boolean prefix match;
- требовать `target_prefix_count >= N`;
- учитывать n-gram score для текущего и конвертированного префикса;
- учитывать пользовательский словарь как override/protection;
- добавить cooldown после отката, чтобы не переключать тот же префикс повторно.

## 6. Системные словари

Основной формат для Linux - Hunspell/MySpell:

- `.dic` - список слов, часто с флагами после `/`;
- `.aff` - правила аффиксов, кодировка и морфология.

Для первого MVP достаточно читать `.dic` и отбрасывать часть после `/`.
Полная поддержка `.aff` даст больше словоформ, но усложнит реализацию. Это можно
оставить на отдельный этап или использовать через библиотеку Hunspell/Enchant.

Ожидаемые пути:

```text
/usr/share/hunspell/*.dic
/usr/share/myspell/dicts/*.dic
/usr/share/myspell/*.dic
```

Команды проверки:

```bash
ls /usr/share/hunspell/*.{dic,aff}
ls /usr/share/myspell/dicts/*.{dic,aff}
```

Нужны английский и русский словари. Типичные имена файлов:

```text
en_US.dic / en_US.aff
ru_RU.dic / ru_RU.aff
```

Возможны варианты `en_GB`, `en_US-large`, `ru_RU_yo`, поэтому loader должен
искать несколько кандидатов и логировать выбранный путь.

## 7. Установка словарей по дистрибутивам

Перед установкой лучше проверить, что уже есть:

```bash
find /usr/share/hunspell /usr/share/myspell /usr/share/myspell/dicts \
  -maxdepth 1 -type f -name '*.dic' 2>/dev/null
```

Debian / Ubuntu / Linux Mint:

```bash
sudo apt install hunspell-en-us hunspell-ru
```

Fedora:

```bash
sudo dnf install hunspell-en-US hunspell-ru
```

Arch Linux / Manjaro:

```bash
sudo pacman -S hunspell-en_us hunspell-ru
```

openSUSE:

```bash
sudo zypper search hunspell-en hunspell-ru myspell-en myspell-ru
sudo zypper install hunspell-en_US hunspell-ru_RU
```

Если точные имена пакетов отличаются в версии дистрибутива, ставить пакеты,
которые создают `en_US.dic` и `ru_RU.dic` в одном из системных путей выше.

## 8. Интеграция с installer/diagnostics

`scripts/install.sh` не должен жестко требовать системные словари, потому что
mid-word режим должен быть optional.

Возможное поведение installer-а:

- если `auto_switch_mid_word` по умолчанию выключен, только вывести подсказку;
- если в будущем пользователь включает этот режим через GUI/CLI, diagnostics
  должны проверять наличие EN/RU `.dic`;
- для Wayland diagnostics можно добавить read-only блок:
  - найден ли `/usr/share/hunspell`;
  - найден ли EN dictionary;
  - найден ли RU dictionary;
  - сколько слов/префиксов загружено.

## 9. Технические риски

Главный риск - ложное переключение до того, как пользователь дописал достаточно
символов. Префиксы часто неоднозначны:

- короткие префиксы слишком общие;
- имена, аббревиатуры, команды shell, код и пароли не похожи на обычные слова;
- системные словари могут быть слишком большими или слишком бедными по
  пользовательскому домену;
- Hunspell `.dic` без `.aff` может не содержать всех словоформ.

Поэтому режим должен быть выключен по умолчанию и иметь быстрый ручной откат.

## 10. MVP-план

Текущий статус:

- `PrefixDictionary` добавлен для встроенных EN/RU словарей;
- `MidWordDetector` добавлен с консервативной политикой:
  source prefix должен отсутствовать, target prefix должен существовать;
- `SystemDictionaryLoader` добавлен как optional Hunspell/MySpell loader;
- config keys добавлены с безопасным `auto_switch_mid_word = false` по умолчанию;
- runtime/input wiring еще не подключен;
- diagnostics для системных словарей еще не подключены.

1. Добавить `PrefixDictionary` со встроенными `en_words.py` / `ru_words.py`.
2. Добавить unit tests на prefix lookup и неоднозначные префиксы.
3. Добавить `SystemDictionaryLoader`, который optional подмешивает Hunspell `.dic`.
4. Добавить `MidWordDetector.should_switch(prefix, current_lang)`.
5. Добавить config/runtime wiring для `auto_switch_mid_word = false`.
6. Добавить `MidWordAutoConversionUseCase` рядом со
   `SpaceAutoConversionUseCase`, используя общий candidate/prefix provider.
7. Подключить use case через `ConversionRuntimeFacade` и input router typing
   flow после обновления `event_buffer`.
8. Реализовать mid-word switch replay и undo marker.
9. Добавить diagnostics и manual QA сценарии.

MVP лучше сначала сделать на встроенных словарях, затем подключать системные.
Так проще отделить алгоритм от проблем наличия пакетов на конкретной системе.
