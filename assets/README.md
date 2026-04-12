# Ассеты LSwitch

## Иконки

Иконка трея генерируется программно в `lswitch/ui/tray_icon.py` (через QPainter) — файлы не нужны.

### Файлы для установки в систему

- `lswitch.svg` — оригинальная SVG иконка
- `lswitch.png` — PNG 64×64
- `lswitch-64.png` — PNG 64×64
- `lswitch-128.png` — PNG 128×128
- `lswitch-256.png` — PNG 256×256

Для установки иконки в меню приложений:

```bash
cp assets/lswitch.png ~/.local/share/icons/lswitch.png
cp config/lswitch-control.desktop ~/.local/share/applications/
```

### Перегенерация PNG

```bash
python3 assets/create_icon.py
```

Требует Pillow (`pip install pillow`).
