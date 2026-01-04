.PHONY: install uninstall start stop restart status enable disable logs clean diagnose

# Установка
install:
	@echo "📦 Установка LSwitch..."
	@sudo bash install.sh

# Удаление
uninstall:
	@echo "🗑️  Удаление LSwitch..."
	@sudo bash uninstall.sh

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

# Диагностика
diagnose:
	@echo "🔍 Диагностика LSwitch..."
	@sudo bash diagnose.sh

# Очистка
clean:
	@rm -rf __pycache__
	@rm -rf *.pyc
	@rm -rf .pytest_cache
	@echo "🧹 Очистка завершена"

# Помощь
help:
	@echo "LSwitch - Команды управления:"
	@echo ""
	@echo "  make install    - Установить в систему"
	@echo "  make uninstall  - Удалить из системы"
	@echo "  make start      - Запустить сервис"
	@echo "  make stop       - Остановить сервис"
	@echo "  make diagnose   - Запустить диагностику"
	@echo "  make restart    - Перезапустить сервис"
	@echo "  make status     - Статус сервиса"
	@echo "  make enable     - Включить автозапуск"
	@echo "  make disable    - Отключить автозапуск"
	@echo "  make logs       - Просмотр логов в реальном времени"
	@echo "  make clean      - Очистить временные файлы"
	@echo ""
