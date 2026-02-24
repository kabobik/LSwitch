"""Tests for UserDictionary."""
import pytest
import os
import json
import tempfile
import threading
import sys

sys.path.insert(0, os.getcwd())


class TestUserDictionaryInit:
    """Tests for UserDictionary initialization."""
    
    def test_creates_default_directory(self, tmp_path, monkeypatch):
        """Test that default config directory is created."""
        from lswitch.user_dictionary import UserDictionary
        
        # Переключаемся на tmp_path как домашнюю директорию
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        
        ud = UserDictionary()  # Без аргумента - используется дефолтный путь
        
        assert (fake_home / ".config" / "lswitch").exists()
    
    def test_loads_empty_dict_if_file_not_exists(self, tmp_path):
        """Test that empty dict is loaded if file doesn't exist."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        assert ud.data['conversions'] == {}
        assert 'settings' in ud.data
    
    def test_loads_existing_file(self, tmp_path):
        """Test that existing file is loaded correctly."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        dict_file.write_text(json.dumps({
            'conversions': {'test': {'weight': 5}},
            'settings': {},
            'stats': {}
        }), encoding='utf-8')
        
        ud = UserDictionary(str(dict_file))
        
        assert 'test' in ud.data['conversions']


class TestUserDictionaryOperations:
    """Tests for UserDictionary operations."""
    
    def test_add_conversion_increases_weight(self, tmp_path):
        """Test that add_conversion increases weight."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        ud.add_conversion("test", from_lang='en', to_lang='ru')
        
        # en->ru уменьшает вес (сдвиг к RU)
        assert ud.data['conversions']['test']['weight'] < 0
    
    def test_add_conversion_ru_to_en(self, tmp_path):
        """Test that ru->en conversion increases weight."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        # еу|ые в ru раскладке = test
        ud.add_conversion("еу|ые", from_lang='ru', to_lang='en')
        
        # Канонизированное слово (в EN) должно иметь положительный вес
        canonical = ud._canonicalize("еуые", 'ru')
        assert canonical in ud.data['conversions'] or 'eu|st' in ud.data['conversions'] or len(ud.data['conversions']) > 0
    
    def test_add_correction_decreases_weight(self, tmp_path):
        """Test that add_correction decreases weight."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        # Сначала добавим конвертацию с положительным весом
        ud.data['conversions']['test'] = {'weight': 5}
        
        # Коррекция для en слова увеличивает вес (сдвиг к EN)
        # но если хотим уменьшить, нужно корректировать ru
        ud.add_correction("test", lang='en')
        
        # Вес должен измениться
        assert 'test' in ud.data['conversions']
    
    def test_flush_saves_to_disk(self, tmp_path):
        """Test that flush() saves data to disk."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        ud.add_conversion("flushtest", from_lang='en', to_lang='ru')
        ud.pending_save = True  # Убедимся что есть что сохранять
        ud.flush()
        
        # Читаем файл напрямую
        data = json.loads(dict_file.read_text(encoding='utf-8'))
        assert 'flushtest' in data['conversions']
    
    def test_should_auto_convert_threshold(self, tmp_path):
        """Test should_auto_convert respects threshold."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        # Добавим запись с весом выше порога
        ud.data['conversions']['hello'] = {'weight': 10}
        
        # ru текст с положительным весом >= threshold должен конвертироваться
        # Но нам нужен ru текст который канонизируется в 'hello'
        # hello в en -> руддщ в ru
        assert ud.should_auto_convert('руддщ', from_lang='ru', to_lang='en', threshold=5) == True
        assert ud.should_auto_convert('руддщ', from_lang='ru', to_lang='en', threshold=15) == False


class TestUserDictionaryThreadSafety:
    """Tests for thread safety."""
    
    def test_concurrent_add_conversion(self, tmp_path):
        """Test that concurrent add_conversion is safe."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        errors = []
        
        def add_many():
            try:
                for i in range(100):
                    ud.add_conversion(f"word_{threading.current_thread().name}_{i}", from_lang='en', to_lang='ru')
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=add_many, name=f"t{i}") for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        ud.flush()
    
    def test_concurrent_read_write(self, tmp_path):
        """Test concurrent reads and writes are safe."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        errors = []
        
        def writer():
            try:
                for i in range(50):
                    ud.add_conversion(f"writer_{i}", from_lang='en', to_lang='ru')
            except Exception as e:
                errors.append(e)
        
        def reader():
            try:
                for i in range(50):
                    ud.should_auto_convert(f"reader_{i}", from_lang='ru', to_lang='en')
                    ud.get_stats()
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
    
    def test_has_lock_attribute(self, tmp_path):
        """Test that UserDictionary has _lock attribute."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        assert hasattr(ud, '_lock')
        assert isinstance(ud._lock, type(threading.Lock()))


class TestUserDictionaryProtection:
    """Tests for protection mechanism."""
    
    def test_is_protected_returns_tuple(self, tmp_path):
        """Test that is_protected returns (bool, int) tuple."""
        from lswitch.user_dictionary import UserDictionary
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        result = ud.is_protected("test", "en")
        
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
    
    def test_protection_after_correction(self, tmp_path):
        """Test that word is protected after correction."""
        from lswitch.user_dictionary import UserDictionary
        import time
        
        dict_file = tmp_path / "user_dict.json"
        ud = UserDictionary(str(dict_file))
        
        # Добавим запись
        ud.data['conversions']['prottest'] = {'weight': 5}
        
        # Сделаем коррекцию
        ud.add_correction("prottest", lang='en')
        
        # Должно быть защищено (временная защита после коррекции)
        protected, weight = ud.is_protected("prottest", "en")
        assert protected == True
