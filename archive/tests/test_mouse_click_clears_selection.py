"""Test that mouse click updates selection snapshot."""
import pytest
import time
import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.getcwd())


def make_lswitch(monkeypatch):
    """Создаёт LSwitch с замоканными зависимостями."""
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    
    class DummyUInput:
        def __init__(self, *a, **k):
            pass
        def write(self, *a, **k):
            pass
        def syn(self):
            pass
    
    monkeypatch.setattr('evdev.UInput', DummyUInput)
    
    from lswitch.core import LSwitch
    ls = LSwitch(config_path='config.json', start_threads=False)
    return ls


def test_mouse_click_updates_selection_snapshot(monkeypatch):
    """После клика мыши last_known_selection должен обновиться."""
    ls = make_lswitch(monkeypatch)
    
    # Устанавливаем старое выделение
    ls.last_known_selection = "old text"
    ls.selection_timestamp = time.time() - 10
    
    # Мокаем system.xclip_get чтобы вернуть пустую строку (пустое поле)
    class MockResult:
        def __init__(self, text):
            self.stdout = text
            self.returncode = 0
    
    monkeypatch.setattr(ls.system, 'xclip_get', lambda *a, **k: MockResult(""))
    ls.update_selection_snapshot()
    
    # После обновления last_known_selection должен стать пустым
    assert ls.last_known_selection == ""


def test_update_selection_snapshot_preserves_text(monkeypatch):
    """update_selection_snapshot сохраняет текущий текст из PRIMARY."""
    ls = make_lswitch(monkeypatch)
    
    # Устанавливаем старое выделение
    ls.last_known_selection = ""
    
    class MockResult:
        def __init__(self, text):
            self.stdout = text
            self.returncode = 0
    
    monkeypatch.setattr(ls.system, 'xclip_get', lambda *a, **k: MockResult("new selection"))
    ls.update_selection_snapshot()
    
    assert ls.last_known_selection == "new selection"


def test_update_selection_snapshot_updates_timestamp(monkeypatch):
    """update_selection_snapshot обновляет selection_timestamp."""
    ls = make_lswitch(monkeypatch)
    
    old_timestamp = time.time() - 100
    ls.selection_timestamp = old_timestamp
    
    class MockResult:
        def __init__(self, text):
            self.stdout = text
            self.returncode = 0
    
    monkeypatch.setattr(ls.system, 'xclip_get', lambda *a, **k: MockResult("text"))
    ls.update_selection_snapshot()
    
    # Timestamp должен обновиться на более свежий
    assert ls.selection_timestamp > old_timestamp
    assert ls.selection_timestamp >= time.time() - 1


def test_update_selection_snapshot_handles_exception(monkeypatch):
    """update_selection_snapshot не падает при ошибках."""
    ls = make_lswitch(monkeypatch)
    
    ls.last_known_selection = "original"
    original_timestamp = ls.selection_timestamp
    
    def raise_error(*a, **k):
        raise Exception("xclip failed")
    
    monkeypatch.setattr(ls.system, 'xclip_get', raise_error)
    
    # Не должно падать
    ls.update_selection_snapshot()
    
    # Значения должны остаться прежними
    assert ls.last_known_selection == "original"
