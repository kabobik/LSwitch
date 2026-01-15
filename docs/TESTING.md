# Тестирование (unit и GUI)

Краткая инструкция по запуску тестов локально и в CI.

## Быстрый старт (локально)

1. Создайте виртуальное окружение и активируйте его (рекомендуется):

```bash
python3 -m venv .venv
. .venv/bin/activate
```

2. Установите зависимости и пакет в editable режиме:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt || true
pip install -e .
pip install pytest
```

3. По умолчанию `pytest` пропускает GUI‑тесты (см. `pytest.ini`). Чтобы запустить обычные тесты:

```bash
pytest
```

## GUI‑тесты (локально)

GUI‑тесты требуют PyQt5 и X‑сервера. На Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3-pyqt5 xvfb python3-xlib xclip xdotool
```

Затем запустите GUI‑тесты под виртуальным X сервером (Xvfb):

```bash
xvfb-run -s "-screen 0 1280x1024x24" pytest -m gui
```

> Примечание: `pytest.ini` содержит маркер `gui`; обычный `pytest` не будет запускать такие тесты.

## Запуск отдельного теста

```bash
pytest tests/test_core.py::test_validate_config_good -q
```

## CI

В репозитории есть GitHub Actions workflow `.github/workflows/python-tests.yml`:
- Job `test` запускает unit-тесты и пропускает GUI-тесты по умолчанию.
- Job `gui-tests` устанавливает PyQt5 и запускает GUI‑тесты под Xvfb.

Если вы добавляете новые GUI‑тесты, пометьте их `@pytest.mark.gui`.

---

Если нужно, добавлю инструкцию по запуску GUI‑тестов в контейнере Docker или с использованием matrix job для нескольких версий Python.