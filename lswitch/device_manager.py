"""Device Manager для LSwitch.

Управляет устройствами ввода с поддержкой hot-plug через udev.
"""

import selectors
import threading
from typing import Dict, Optional, Callable, Iterator
import evdev
from evdev import ecodes

try:
    import pyudev
    PYUDEV_AVAILABLE = True
except ImportError:
    PYUDEV_AVAILABLE = False


class DeviceManager:
    """Управляет устройствами ввода."""
    
    def __init__(self, debug: bool = False, 
                 on_device_added: Optional[Callable] = None,
                 on_device_removed: Optional[Callable] = None):
        self.debug = debug
        self.devices: Dict[str, evdev.InputDevice] = {}
        self.selector = selectors.DefaultSelector()
        self.on_device_added = on_device_added
        self.on_device_removed = on_device_removed
        self._lock = threading.Lock()
        self._udev_monitor = None
        self._udev_thread = None
        self._running = False
        self._virtual_kb_name = None  # Имя виртуальной клавиатуры LSwitch для фильтрации
    
    def set_virtual_kb_name(self, name: str):
        """Установить имя виртуальной клавиатуры для фильтрации."""
        self._virtual_kb_name = name
    
    def scan_devices(self) -> int:
        """Сканирует /dev/input/ и регистрирует подходящие устройства.
        
        Returns:
            Количество зарегистрированных устройств.
        """
        count = 0
        for path in evdev.list_devices():
            if self._try_add_device(path):
                count += 1
        return count
    
    def _is_suitable_device(self, device: evdev.InputDevice) -> bool:
        """Проверяет подходит ли устройство для мониторинга."""
        # Фильтруем виртуальную клавиатуру LSwitch
        if self._virtual_kb_name and self._virtual_kb_name in device.name:
            return False
        
        caps = device.capabilities()
        if ecodes.EV_KEY not in caps:
            return False
        
        keys = caps.get(ecodes.EV_KEY, [])
        
        # Клавиатура: есть KEY_A
        is_keyboard = ecodes.KEY_A in keys
        
        # Мышь: есть BTN_LEFT или BTN_RIGHT
        is_mouse = ecodes.BTN_LEFT in keys or ecodes.BTN_RIGHT in keys
        
        return is_keyboard or is_mouse
    
    def _try_add_device(self, path: str) -> bool:
        """Пытается добавить устройство по пути.
        
        Returns:
            True если устройство добавлено успешно.
        """
        with self._lock:
            if path in self.devices:
                return False
            
            try:
                device = evdev.InputDevice(path)
                if not self._is_suitable_device(device):
                    device.close()
                    return False
                
                self.devices[path] = device
                self.selector.register(device, selectors.EVENT_READ)
                
                if self.debug:
                    print(f"✓ Устройство добавлено: {device.name} ({path})", flush=True)
                
                if self.on_device_added:
                    try:
                        self.on_device_added(device)
                    except Exception:
                        pass
                
                return True
                
            except (OSError, PermissionError) as e:
                if self.debug:
                    print(f"⚠️ Не удалось добавить {path}: {e}", flush=True)
                return False
    
    def remove_device(self, path: str) -> bool:
        """Безопасно удаляет устройство.
        
        Returns:
            True если устройство было удалено.
        """
        with self._lock:
            device = self.devices.pop(path, None)
            if device is None:
                return False
            
            try:
                self.selector.unregister(device)
            except Exception:
                pass
            
            device_name = device.name
            try:
                device.close()
            except Exception:
                pass
            
            if self.debug:
                print(f"✗ Устройство отключено: {device_name} ({path})", flush=True)
            
            if self.on_device_removed:
                try:
                    self.on_device_removed(device)
                except Exception:
                    pass
            
            return True
    
    def handle_read_error(self, device: evdev.InputDevice, error: Exception):
        """Обрабатывает ошибку чтения — graceful removal."""
        path = device.path
        if self.debug:
            print(f"⚠️ Ошибка чтения {device.name}: {error}", flush=True)
        self.remove_device(path)
    
    def get_events(self, timeout: float = 0.1) -> Iterator[tuple]:
        """Итератор событий со всех устройств.
        
        Yields:
            (device, event) кортежи.
        """
        ready = self.selector.select(timeout=timeout)
        for key, mask in ready:
            device = key.fileobj
            try:
                for event in device.read():
                    yield (device, event)
            except (OSError, IOError) as e:
                self.handle_read_error(device, e)
    
    def start_udev_monitor(self):
        """Запускает udev мониторинг hot-plug в отдельном потоке."""
        if not PYUDEV_AVAILABLE:
            if self.debug:
                print("⚠️ pyudev не установлен — hot-plug отключен", flush=True)
            return False
        
        if self._udev_thread and self._udev_thread.is_alive():
            return True
        
        self._running = True
        self._udev_thread = threading.Thread(target=self._udev_monitor_loop, daemon=True)
        self._udev_thread.start()
        
        if self.debug:
            print("✓ udev мониторинг запущен", flush=True)
        return True
    
    def _udev_monitor_loop(self):
        """Цикл мониторинга udev событий."""
        try:
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by(subsystem='input')
            monitor.start()
            
            while self._running:
                device = monitor.poll(timeout=1)
                if device is None:
                    continue
                
                # Получаем /dev/input/eventX путь
                dev_path = device.device_node
                if not dev_path or not dev_path.startswith('/dev/input/event'):
                    continue
                
                if device.action == 'add':
                    # Небольшая задержка чтобы устройство успело инициализироваться
                    import time
                    time.sleep(0.1)
                    self._try_add_device(dev_path)
                elif device.action == 'remove':
                    self.remove_device(dev_path)
                    
        except Exception as e:
            if self.debug:
                print(f"⚠️ Ошибка udev монитора: {e}", flush=True)
    
    def stop_udev_monitor(self):
        """Останавливает udev мониторинг."""
        self._running = False
        if self._udev_thread:
            self._udev_thread.join(timeout=2)
            self._udev_thread = None
    
    def close(self):
        """Освобождает все ресурсы."""
        self.stop_udev_monitor()
        
        with self._lock:
            for path in list(self.devices.keys()):
                device = self.devices.pop(path, None)
                if device:
                    try:
                        self.selector.unregister(device)
                    except Exception:
                        pass
                    try:
                        device.close()
                    except Exception:
                        pass
            
            try:
                self.selector.close()
            except Exception:
                pass
    
    @property
    def device_count(self) -> int:
        """Количество активных устройств."""
        return len(self.devices)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
