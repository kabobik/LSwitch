# Архитектура LSwitch - Модульная система адаптеров

## Обзор

LSwitch теперь имеет модульную архитектуру, которая позволяет поддерживать различные окружения рабочего стола (DE) и display серверы без изменения основного кода.

## Структура проекта

```
LSwitch/
├── lswitch.py              # Основной демон (XKB, clipboard, словарь)
├── lswitch_control.py      # GUI панель управления (модульная версия)
├── utils/                  # Утилиты
│   ├── desktop.py         # Определение DE и display server
│   └── theme.py           # Чтение цветов темы из разных DE
├── adapters/              # Адаптеры для разных DE
│   ├── base.py           # Абстрактный базовый класс
│   ├── cinnamon.py       # Адаптер для Cinnamon
│   └── kde.py            # Адаптер для KDE Plasma
└── drivers/              # Драйверы для display серверов (планируется)
    ├── x11.py            # X11/Xlib (текущий)
    └── wayland.py        # Wayland (TODO)
```

## Модули

### utils/desktop.py

Определяет текущее окружение рабочего стола и display сервер.

**Функции:**
- `detect_desktop_environment()` - Возвращает `'cinnamon'`, `'kde'`, `'gnome'`, `'xfce'`, `'mate'` или `'generic'`
- `detect_display_server()` - Возвращает `'wayland'` или `'x11'`
- `get_environment_info()` - Возвращает словарь с полной информацией

**Пример:**
```python
from utils.desktop import detect_desktop_environment, detect_display_server

de = detect_desktop_environment()  # 'kde'
display = detect_display_server()  # 'x11'
```

### utils/theme.py

Читает цвета темы из файлов конфигурации различных DE.

**Функции:**
- `get_cinnamon_theme_colors()` - Парсит GTK CSS файлы (`/usr/share/themes/*/gtk-3.0/gtk.css`)
- `get_kde_theme_colors()` - Читает `~/.config/kdeglobals` секции `[Colors:Window]` и `[Colors:View]`
- `get_theme_colors(de_name)` - Универсальный интерфейс
- `get_default_dark_colors()` - Fallback цвета темной темы

**Формат возвращаемых данных:**
```python
{
    'bg_color': (42, 46, 50),      # RGB фона
    'fg_color': (252, 252, 252),   # RGB текста
    'base_color': (27, 30, 32)     # RGB base (для полей ввода)
}
```

### adapters/base.py

Абстрактный базовый класс для всех адаптеров GUI.

**Методы:**
- `create_menu(parent=None)` - Создаёт меню (QMenu или CustomMenu)
- `get_theme_colors()` - Возвращает цвета темы
- `supports_native_menu()` - Возвращает `True` если поддерживается нативное QMenu

### adapters/cinnamon.py

Адаптер для Linux Mint Cinnamon.

**Особенности:**
- Использует `CustomMenu` (QWidget) вместо QMenu
- Причина: Cinnamon перехватывает QMenu и игнорирует Qt stylesheets
- `QMenuWrapper` обеспечивает совместимость API с QMenu
- Читает цвета из GTK темы (`/usr/share/themes/*/gtk-3.0/gtk.css`)

**Компоненты:**
- `CustomMenuItem` - кастомный пункт меню (48px высота, 24px шрифт)
- `CustomMenuSeparator` - разделитель (1px линия)
- `CustomMenu` - всплывающее окно с пунктами меню
- `QMenuWrapper` - обертка для совместимости с QMenu API

### adapters/kde.py

Адаптер для KDE Plasma.

**Особенности:**
- Использует нативное `QMenu`
- KDE корректно применяет QPalette к QMenu
- Читает цвета из `~/.config/kdeglobals`
- Применяет цвета через `QPalette` и `QMenu.setStyleSheet()`

**Преимущества:**
- Полная интеграция с темой Breeze/Breeze Dark
- Не требует кастомных виджетов
- Автоматическая поддержка анимаций и эффектов KDE

## Как добавить поддержку нового DE

### Шаг 1: Добавить определение в utils/desktop.py

```python
def detect_desktop_environment():
    # ... существующий код ...
    
    # Добавьте проверку для вашего DE
    if 'MYNEWDE' in desktop.upper():
        return 'mynewde'
```

### Шаг 2: Добавить чтение темы в utils/theme.py

```python
def get_mynewde_theme_colors():
    """Читает цвета темы MyNewDE"""
    try:
        # Читайте конфиг файл вашего DE
        # Верните словарь с bg_color, fg_color, base_color
        return {
            'bg_color': (R, G, B),
            'fg_color': (R, G, B),
            'base_color': (R, G, B)
        }
    except Exception:
        return None

def get_theme_colors(de_name):
    # ... существующий код ...
    elif de_name == 'mynewde':
        return get_mynewde_theme_colors()
```

### Шаг 3: Создать адаптер adapters/mynewde.py

```python
from PyQt5.QtWidgets import QMenu
from adapters.base import BaseGUIAdapter
from utils.theme import get_mynewde_theme_colors

class MyNewDEAdapter(BaseGUIAdapter):
    def __init__(self):
        super().__init__()
        self.theme_colors = self.get_theme_colors()
    
    def create_menu(self, parent=None):
        """Создаёт меню для MyNewDE"""
        menu = QMenu(None)
        # Применяем стили...
        return menu
    
    def get_theme_colors(self):
        colors = get_mynewde_theme_colors()
        if not colors:
            from utils.theme import get_default_dark_colors
            colors = get_default_dark_colors()
        return colors
    
    def supports_native_menu(self):
        # True если ваше DE поддерживает QMenu с темами
        # False если нужен CustomMenu
        return True
```

### Шаг 4: Обновить фабрику в adapters/__init__.py

```python
from adapters.mynewde import MyNewDEAdapter

def get_adapter():
    de = detect_desktop_environment()
    
    if de == 'cinnamon':
        return CinnamonAdapter()
    elif de == 'kde':
        return KDEAdapter()
    elif de == 'mynewde':
        return MyNewDEAdapter()
    else:
        # Fallback
        return CinnamonAdapter()
```

## Тестирование

Используйте `test_adapters.py` для проверки:

```bash
python3 test_adapters.py
```

Вывод покажет:
- Определённое DE и display server
- Выбранный адаптер
- Прочитанные цвета темы
- Результат создания меню

## Поддерживаемые DE

| DE | Статус | Адаптер | Меню | Тема |
|----|--------|---------|------|------|
| **Cinnamon** | ✅ Полная | CinnamonAdapter | CustomMenu (QWidget) | GTK CSS |
| **KDE Plasma** | ✅ Полная | KDEAdapter | QMenu (нативное) | kdeglobals |
| GNOME Shell | ⏳ Планируется | - | - | - |
| XFCE | ⏳ Планируется | - | - | - |
| MATE | ⏳ Планируется | - | - | - |

## Roadmap

### Краткосрочный план
- [x] Модульная архитектура
- [x] Адаптер для Cinnamon
- [x] Адаптер для KDE Plasma
- [ ] Тестирование на реальном Cinnamon
- [ ] Тестирование на KDE Wayland

### Долгосрочный план
- [ ] Адаптер для GNOME Shell
- [ ] Адаптер для XFCE
- [ ] Driver abstraction для X11/Wayland
- [ ] Wayland driver через DBus/ydotool
- [ ] Поддержка KWin скриптов для Wayland

## Технические детали

### Почему CustomMenu для Cinnamon?

Cinnamon использует Muffin (форк Mutter) как композитор. При показе QMenu в системном трее, Muffin перехватывает меню и рендерит его собственными средствами, игнорируя Qt stylesheets и QPalette.

**Решение:** CustomMenu - это QWidget с флагом Qt.Popup, который Cinnamon не перехватывает.

### Почему нативное QMenu для KDE?

KDE Plasma использует KWin, который корректно взаимодействует с Qt приложениями. QMenu полностью поддерживает темизацию через QPalette и интегрируется с темой Breeze.

**Преимущества нативного QMenu:**
- Анимации и эффекты KDE
- Автоматическая адаптация под тему
- Shadows и compositing эффекты
- Нативный look & feel

### Как работает QMenuWrapper?

`QMenuWrapper` в [adapters/cinnamon.py](adapters/cinnamon.py) оборачивает `CustomMenu` и предоставляет API совместимый с `QMenu`:

```python
class QMenuWrapper:
    def addAction(self, action_or_text):
        # Преобразует QAction в CustomMenuItem
        # Синхронизирует состояние (checked, enabled)
        
    def addSeparator(self):
        # Добавляет CustomMenuSeparator
        
    def popup(self, pos):
        # Показывает CustomMenu выше курсора
```

Это позволяет `lswitch_control.py` использовать единый код для обоих адаптеров:

```python
menu = adapter.create_menu()  # QMenu или QMenuWrapper
menu.addAction(action)         # Работает в обоих случаях
menu.addSeparator()           # Работает в обоих случаях
```

## Зависимости

```
PyQt5 >= 5.15.0
```

Опционально:
- `python3-gi` для доступа к GTK темам (Cinnamon)
- `kdeglobals` файл для KDE тем (обычно есть)

## Лицензия

MIT License - см. [LICENSE](LICENSE)
