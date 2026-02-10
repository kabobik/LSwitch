.PHONY: install uninstall start stop restart status enable disable logs clean test post-install help

# ═══════════════════════════════════════════
# Установка / удаление (единственный способ)
# ═══════════════════════════════════════════

install:
	@echo "📦 Установка LSwitch..."
	@sudo pip3 install -e .
	@$(MAKE) post-install
	@echo "✅ Установка завершена!"
	@echo ""
	@echo "Запуск:  make enable   (автостарт + запуск)"
	@echo "GUI:     lswitch-control"

post-install:
	@echo "🔐 Настройка прав..."
	@sudo usermod -a -G input $(USER) 2>/dev/null || true
	@sudo udevadm control --reload-rules 2>/dev/null || true
	@sudo udevadm trigger 2>/dev/null || true
	@systemctl --user daemon-reload 2>/dev/null || true

uninstall:
	@echo "🗑️  Удаление LSwitch..."
	@systemctl --user stop lswitch 2>/dev/null || true
	@systemctl --user disable lswitch 2>/dev/null || true
	@sudo pip3 uninstall -y lswitch
	@echo "✅ Удалено"

# ═══════════════════════════════════════════
# Управление сервисом (user-level systemd)
# ═══════════════════════════════════════════

start:
	@systemctl --user start lswitch
	@systemctl --user status lswitch --no-pager

stop:
	@systemctl --user stop lswitch

restart:
	@systemctl --user restart lswitch
	@systemctl --user status lswitch --no-pager

status:
	@systemctl --user status lswitch --no-pager || true

enable:
	@systemctl --user enable lswitch
	@systemctl --user start lswitch
	@echo "✅ Автозапуск включён"

disable:
	@systemctl --user disable lswitch
	@echo "❌ Автозапуск отключён"

logs:
	@journalctl --user-unit=lswitch -f

# ═══════════════════════════════════════════
# Разработка
# ═══════════════════════════════════════════

test:
	@pytest -v

clean:
	@rm -rf __pycache__ .pytest_cache build dist *.egg-info
	@find . -name '*.pyc' -delete
	@echo "🧹 Очистка завершена"

help:
	@echo "LSwitch — команды:"
	@echo ""
	@echo "  make install    Установить (pip + права + systemd)"
	@echo "  make uninstall  Удалить"
	@echo ""
	@echo "  make start      Запустить демон"
	@echo "  make stop       Остановить"
	@echo "  make restart    Перезапустить"
	@echo "  make status     Статус"
	@echo "  make enable     Автозапуск ON"
	@echo "  make disable    Автозапуск OFF"
	@echo "  make logs       Логи (follow)"
	@echo ""
	@echo "  make test       Тесты"
	@echo "  make clean      Очистка"
