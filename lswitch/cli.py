"""Entry point for LSwitch (CLI)"""
import sys
import os
import signal

# Import LSwitch lazily to avoid heavy imports at module import time
from .core import LSwitch


def main():
    """Точка входа для запуска приложения"""
    # Не переназначаем sys.stdout/sys.stderr здесь — это ломает pytest capture.
    # systemd запускает Python с -u или можно настроить unit с Environment=PYTHONUNBUFFERED=1
    # При необходимости можно включить line buffering только в реальной службе.

    # Проверяем доступ к устройствам (не требуем root если пользователь в группе input)
    try:
        import evdev
        devices = evdev.list_devices()
        if not devices:
            print("❌ Не найдено устройств ввода", flush=True)
            print("   Проверьте что пользователь в группе input: groups | grep input", flush=True)
            sys.exit(126)
    except PermissionError:
        print("❌ Нет доступа к /dev/input/", flush=True)
        print("   Добавьте пользователя в группу input: sudo usermod -aG input $USER", flush=True)
        print("   После этого перезайдите в систему", flush=True)
        sys.exit(126)

    print("🚀 LSwitch запущен", flush=True)
    print("   Двойное нажатие Shift = конвертация последнего слова", flush=True)
    print("   Ctrl+C = выход", flush=True)
    print(flush=True)

    # Создаем экземпляр приложения
    app = LSwitch()

    # Обработчик SIGHUP для перезагрузки конфигурации
    def handle_sighup(signum, frame):
        print("📥 Получен сигнал SIGHUP - запрос перезагрузки конфига", flush=True)
        app.config_reload_requested = True

    signal.signal(signal.SIGHUP, handle_sighup)

    try:
        app.run()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
