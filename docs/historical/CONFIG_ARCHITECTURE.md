# Архитектура системы конфигурации LSwitch

## Обзор

Конфигурация LSwitch реализована в едином модуле `lswitch/config.py` и предоставляет два интерфейса:

1. **Функциональный интерфейс** - простые функции для загрузки и валидации 
2. **Объектный интерфейс** - класс `ConfigManager` для управления состоянием конфигурации

## Модули

### `lswitch/config.py`

Основной модуль конфигурации, содержит:

#### Функции

**`load_config(config_path: str, debug: bool = False) -> dict`**

Загружает конфигурацию из файла и мерджит с пользовательскими переопределениями.

```python
from lswitch.config import load_config

# Используется в CLI
cfg = load_config('/etc/lswitch/config.json', debug=True)
```

**`validate_config(conf: dict) -> dict`**

Валидирует и нормализует конфигурационный словарь. Применяет значения по умолчанию и проверяет типы.

```python
from lswitch.config import validate_config

validated = validate_config({'debug': True})
```

#### Класс `ConfigManager`

Управляет конфигурацией с состоянием, поддерживает реальные операции (load, save, reload).

```python
from lswitch.config import ConfigManager

# Инициализация (auto-detect конфиг файл)
cm = ConfigManager()

# Или явный путь
cm = ConfigManager(config_path='/etc/lswitch/config.json')

# Получение значений
debug = cm.get('debug')
all_config = cm.get_all()

# Установка значений
cm.set('debug', True)
cm.update({'auto_switch': False, 'user_dict_enabled': True})

# Сохранение на диск
cm.save()

# Перезагрузка из файла
cm.reload()

# Валидация
is_valid = cm.validate()

# Сброс на умолчания
cm.reset_to_defaults()
```

## Использование

### CLI (lswitch.cli)

Использует функциональный интерфейс:

```python
from lswitch.config import load_config

config = load_config(args.config, args.debug)
```

### Core приложение (lswitch.core)

Использует функциональный интерфейс для загрузки и валидации:

```python
from lswitch.config import load_config, validate_config
```

### GUI (lswitch_control.py)

Использует объектный интерфейс для управления состоянием:

```python
from lswitch.config import ConfigManager

self.config_manager = ConfigManager()
self.config = self.config_manager.get_all()

# После изменения пользователем
self.config_manager.save()
```

## Порядок загрузки конфигурации

`ConfigManager` загружает конфигурацию в следующем порядке приоритета:

1. Системная конфигурация: `/etc/lswitch/config.json` (если существует)
2. Или конфигурация пользователя: `~/.config/lswitch/config.json` (если существует)
3. Или создается при сохранении в `~/.config/lswitch/config.json`
4. Пользовательская конфигурация **всегда** мерджится сверху (переопределяет системную)

## Параметры конфигурации

Все параметры определены в `DEFAULT_CONFIG`:

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|---------|
| `double_click_timeout` | float | 0.3 | Таймаут двойного нажатия Shift (сек) |
| `debug` | bool | False | Включить отладочный вывод |
| `switch_layout_after_convert` | bool | True | Переключать раскладку после конвертации |
| `layout_switch_key` | str | 'Alt_L+Shift_L' | Горячая клавиша переключения раскладки |
| `auto_switch` | bool | False | Автопереключение раскладки |
| `user_dict_enabled` | bool | False | Включить самообучающийся словарь |
| `user_dict_min_weight` | int | 2 | Минимальный вес слова в словаре |

## Обратная совместимость

`ConfigManager` доступен через несколько путей для обратной совместимости:

```python
# Все эти импорты работают и обращаются к одному классу:
from lswitch.config import ConfigManager
from lswitch.managers import ConfigManager  # через re-export
```

## История консолидации

До консолидации были два модуля:
- `lswitch/config.py` - простые функции
- `lswitch/managers/config_manager.py` - класс ConfigManager

**Проблемы:**
- Дублирование логики загрузки
- Разные DEFAULT_CONFIG значения
- Путаница какой модуль использовать

**Решение:**
- Объединены оба интерфейса в `lswitch/config.py`
- Удален `lswitch/managers/config_manager.py`
- Добавлен re-export через `lswitch/managers/__init__.py` для обратной совместимости
