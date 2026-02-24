#!/usr/bin/env python3
"""
Проверка всех зависимостей LSwitch
Используется в install.sh и может быть запущен отдельно
"""

import sys
import shutil
import subprocess
from typing import List, Tuple

# Цветной вывод
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

class DependencyChecker:
    """Проверяет зависимости LSwitch"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.ok: List[str] = []
    
    def check_python_version(self) -> bool:
        """Проверка версии Python"""
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.errors.append(f"Python 3.8+ требуется (найдено {version.major}.{version.minor})")
            return False
        self.ok.append(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    
    def check_python_packages(self) -> bool:
        """Проверка Python пакетов"""
        packages = {
            'evdev': 'критично',
            'Xlib': 'рекомендуется',
            'PyQt5': 'для GUI',
        }
        
        all_ok = True
        for pkg, importance in packages.items():
            try:
                __import__(pkg)
                self.ok.append(f"Python: {pkg}")
            except ImportError:
                if importance == 'критично':
                    self.errors.append(f"Python пакет '{pkg}' не найден ({importance})")
                    all_ok = False
                else:
                    self.warnings.append(f"Python пакет '{pkg}' не найден ({importance})")
        
        return all_ok
    
    def check_system_tools(self) -> bool:
        """Проверка системных утилит"""
        tools = {
            'xclip': 'критично',
            'xdotool': 'критично',
        }
        
        all_ok = True
        for tool, importance in tools.items():
            if shutil.which(tool):
                self.ok.append(f"Утилита: {tool}")
            else:
                if importance == 'критично':
                    self.errors.append(f"Утилита '{tool}' не найдена ({importance})")
                    all_ok = False
                else:
                    self.warnings.append(f"Утилита '{tool}' не найдена ({importance})")
        
        return all_ok
    
    def check_commands(self) -> bool:
        """Проверка entry points"""
        commands = ['lswitch', 'lswitch-control']
        
        for cmd in commands:
            if shutil.which(cmd):
                self.ok.append(f"Команда: {cmd}")
            else:
                self.warnings.append(f"Команда '{cmd}' не найдена в PATH")
        
        return True  # Не критично
    
    def check_display_server(self) -> None:
        """Проверка display server"""
        import os
        session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')
        
        if session_type == 'wayland':
            self.warnings.append("Обнаружен Wayland (LSwitch оптимизирован для X11)")
        elif session_type == 'x11':
            self.ok.append("Display: X11")
        else:
            self.warnings.append(f"Неизвестный display server: {session_type}")
    
    def check_input_group(self) -> bool:
        """Проверка группы input"""
        import os
        import grp
        import pwd
        
        try:
            # Получаем имя пользователя через несколько способов
            try:
                username = os.getlogin()
            except (OSError, AttributeError):
                username = pwd.getpwuid(os.getuid()).pw_name
            
            # Получаем группы пользователя
            user_gids = os.getgrouplist(username, pwd.getpwnam(username).pw_gid)
            user_groups = [grp.getgrgid(gid).gr_name for gid in user_gids]
            
            if 'input' in user_groups:
                self.ok.append(f"Пользователь {username} в группе input")
                return True
            else:
                self.errors.append(
                    f"Пользователь {username} НЕ в группе input!\n"
                    f"      LSwitch не будет иметь доступа к /dev/input.\n"
                    f"      Решение: sudo usermod -a -G input {username}\n"
                    f"      Затем перелогиниться (logout → login)"
                )
                return False
        except Exception as e:
            self.warnings.append(f"Не удалось проверить группу input: {e}")
            return True  # Не критично для продолжения проверок
    
    def run_all_checks(self) -> bool:
        """Запуск всех проверок"""
        print("🔍 Проверка зависимостей LSwitch...\n")
        
        checks = [
            self.check_python_version,
            self.check_python_packages,
            self.check_system_tools,
            self.check_commands,
            self.check_input_group,  # Критичная проверка!
        ]
        
        critical_ok = all(check() for check in checks)
        
        # Некритичные проверки
        self.check_display_server()
        
        return critical_ok
    
    def print_results(self) -> None:
        """Вывод результатов"""
        print()
        
        if self.ok:
            print(f"{GREEN}✅ Установлено:{NC}")
            for item in self.ok:
                print(f"   {GREEN}✓{NC} {item}")
            print()
        
        if self.warnings:
            print(f"{YELLOW}⚠️  Предупреждения:{NC}")
            for item in self.warnings:
                print(f"   {YELLOW}⚠{NC} {item}")
            print()
        
        if self.errors:
            print(f"{RED}❌ Критические проблемы:{NC}")
            for item in self.errors:
                print(f"   {RED}✗{NC} {item}")
            print()
            return False
        
        if not self.warnings:
            print(f"{GREEN}✅ Все зависимости установлены!{NC}")
        else:
            print(f"{GREEN}✅ Критичные зависимости установлены{NC}")
            print(f"{YELLOW}⚠️  Есть некритичные предупреждения{NC}")
        
        return True


def main() -> int:
    """Main entry point"""
    checker = DependencyChecker()
    
    try:
        checks_ok = checker.run_all_checks()
        results_ok = checker.print_results()
        
        if checks_ok and results_ok:
            return 0
        elif checks_ok:
            return 0  # Только предупреждения - OK
        else:
            return 1
    except KeyboardInterrupt:
        print("\n❌ Прервано пользователем")
        return 130
    except Exception as e:
        print(f"\n{RED}❌ Ошибка: {e}{NC}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
