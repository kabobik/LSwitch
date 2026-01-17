.PHONY: install uninstall start stop restart status enable disable logs clean test

# Установка (используется setup.py через pip)
install:
	@echo "📦 Установка LSwitch..."
	@sudo pip3 install -e .

# Удаление
uninstall:
	@echo "🗑️  Удаление LSwitch..."
	@sudo pip3 uninstall -y lswitch

# Управление сервисом
start:
	@echo "▶️  Запуск LSwitch..."
	@sudo systemctl start lswitch
	@sudo systemctl status lswitch --no-pager

stop:
	@echo "⏸️  Остановка LSwitch..."
	@sudo systemctl stop lswitch

restart:
	@echo "🔄 Перезапуск LSwitch..."
	@sudo systemctl restart lswitch
	@sudo systemctl status lswitch --no-pager

status:
	@sudo systemctl status lswitch --no-pager

enable:
	@echo "✅ Включение автозапуска..."
	@sudo systemctl enable lswitch
	@sudo systemctl start lswitch

disable:
	@echo "❌ Отключение автозапуска..."
	@sudo systemctl disable lswitch

# Просмотр логов
logs:
	@sudo journalctl -u lswitch -f

# Тестирование
test:
	@echo "🧪 Запуск тестов..."
	@pytest -v

# Очистка
clean:
	@rm -rf __pycache__
	@rm -rf *.pyc
	@rm -rf .pytest_cache
	@rm -rf build dist *.egg-info
	@echo "🧹 Очистка завершена"

# Помощь
help:
	@echo "LSwitch - Команды управления:"
	@echo ""
	@echo "  make install    - Установить в систему (pip3)"
	@echo "  make uninstall  - Удалить из системы"
	@echo "  make start      - Запустить сервис"
	@echo "  make stop       - Остановить сервис"
	@echo "  make restart    - Перезапустить сервис"
	@echo "  make status     - Статус сервиса"
	@echo "  make enable     - Включить автозапуск"
	@echo "  make disable    - Отключить автозапуск"
	@echo "  make logs       - Просмотр логов в реальном времени"
	@echo "  make test       - Запустить тесты (pytest)"
	@echo "  make clean      - Очистить временные файлы"
	@echo ""
