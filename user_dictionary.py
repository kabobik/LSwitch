#!/usr/bin/env python3
"""
Пользовательский словарь - самообучающаяся система
Запоминает слова, которые пользователь исправляет после автоконвертации
"""

import json
import os
from datetime import datetime
from pathlib import Path


class UserDictionary:
    """Управление пользовательским словарём с весами"""
    
    def __init__(self, config_dir=None):
        """
        Args:
            config_dir: Директория для хранения словаря
                       По умолчанию: ~/.config/lswitch/
        """
        if config_dir is None:
            config_dir = os.path.expanduser('~/.config/lswitch')
        
        self.config_dir = Path(config_dir)
        self.dict_file = self.config_dir / 'user_dict.json'
        
        # Создаём директорию если не существует
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Загружаем словарь
        self.data = self._load()
    
    def _load(self):
        """Загружает словарь из файла"""
        if not self.dict_file.exists():
            return {
                'words': {},
                'settings': {
                    'min_weight': 2,      # Минимальный вес для применения
                    'max_words': 1000,    # Максимум слов в словаре
                    'correction_timeout': 5.0  # Таймаут для связи коррекции с автоконвертацией (сек)
                },
                'stats': {
                    'total_corrections': 0,
                    'created_at': datetime.now().isoformat()
                }
            }
        
        try:
            with open(self.dict_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Ошибка загрузки user_dict: {e}")
            return self._load()  # Возвращаем пустой
    
    def _save(self):
        """Сохраняет словарь в файл"""
        try:
            with open(self.dict_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  Ошибка сохранения user_dict: {e}")
    
    def add_correction(self, word, lang, debug=False):
        """
        Добавляет слово в словарь или увеличивает его вес
        
        Args:
            word: Исправленное слово (правильное)
            lang: Язык слова ('ru' или 'en')
            debug: Вывод отладочной информации
        """
        word_lower = word.lower()
        
        if word_lower in self.data['words']:
            # Слово уже есть - увеличиваем вес
            self.data['words'][word_lower]['weight'] += 1
            self.data['words'][word_lower]['last_seen'] = datetime.now().isoformat()
            
            if debug:
                weight = self.data['words'][word_lower]['weight']
                print(f"📚 User Dict: '{word}' вес увеличен → {weight}")
        else:
            # Новое слово
            self.data['words'][word_lower] = {
                'weight': 1,
                'lang': lang,
                'added_at': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat()
            }
            
            if debug:
                print(f"📚 User Dict: Добавлено '{word}' (lang: {lang})")
        
        # Увеличиваем счётчик
        self.data['stats']['total_corrections'] += 1
        
        # Проверяем лимит слов
        self._check_limit()
        
        # Сохраняем
        self._save()
    
    def _check_limit(self):
        """Проверяет лимит слов и удаляет самые старые с малым весом"""
        max_words = self.data['settings']['max_words']
        
        if len(self.data['words']) > max_words:
            # Сортируем по весу (меньше) и дате (старее)
            sorted_words = sorted(
                self.data['words'].items(),
                key=lambda x: (x[1]['weight'], x[1]['last_seen'])
            )
            
            # Удаляем 10% самых слабых
            to_remove = int(max_words * 0.1)
            for word, _ in sorted_words[:to_remove]:
                del self.data['words'][word]
    
    def is_protected(self, word, lang):
        """
        Проверяет защищено ли слово (вес >= min_weight)
        
        Args:
            word: Слово для проверки
            lang: Язык слова
            
        Returns:
            (bool, int): (защищено, вес)
        """
        word_lower = word.lower()
        
        if word_lower not in self.data['words']:
            return (False, 0)
        
        entry = self.data['words'][word_lower]
        
        # Проверяем язык и вес
        if entry['lang'] == lang:
            weight = entry['weight']
            min_weight = self.data['settings']['min_weight']
            return (weight >= min_weight, weight)
        
        return (False, entry['weight'])
    
    def add_conversion(self, word, from_lang, to_lang, debug=False):
        """
        Добавляет успешную конвертацию с направлением
        
        Args:
            word: Исходное слово
            from_lang: Язык исходного слова
            to_lang: Язык после конвертации
            debug: Вывод отладочной информации
        """
        word_lower = word.lower()
        
        # Создаём ключ с направлением конвертации
        conv_key = f"{word_lower}:{from_lang}->{to_lang}"
        
        if 'conversions' not in self.data:
            self.data['conversions'] = {}
        
        if conv_key in self.data['conversions']:
            # Конвертация уже есть - увеличиваем вес
            self.data['conversions'][conv_key]['weight'] += 1
            self.data['conversions'][conv_key]['last_seen'] = datetime.now().isoformat()
            
            if debug:
                weight = self.data['conversions'][conv_key]['weight']
                print(f"📚 Conversion: '{word}' ({from_lang}→{to_lang}) вес увеличен → {weight}")
        else:
            # Новая конвертация
            self.data['conversions'][conv_key] = {
                'word': word_lower,
                'from_lang': from_lang,
                'to_lang': to_lang,
                'weight': 1,
                'added_at': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat()
            }
            
            if debug:
                print(f"📚 Conversion: Добавлена '{word}' ({from_lang}→{to_lang})")
        
        # Сохраняем
        self._save()
    
    def get_conversion_weight(self, word, from_lang, to_lang):
        """
        Получает вес конвертации
        
        Returns:
            int: Вес конвертации (0 если нет в словаре)
        """
        if 'conversions' not in self.data:
            return 0
        
        word_lower = word.lower()
        conv_key = f"{word_lower}:{from_lang}->{to_lang}"
        
        if conv_key in self.data['conversions']:
            return self.data['conversions'][conv_key]['weight']
        
        return 0
    
    def should_auto_convert(self, word, from_lang, to_lang, threshold=5):
        """
        Проверяет нужна ли автоконвертация для слова
        
        Args:
            word: Слово для проверки
            from_lang: Текущий язык
            to_lang: Целевой язык
            threshold: Минимальный вес для автоконвертации (по умолчанию 5)
            
        Returns:
            bool: True если нужна автоконвертация
        """
        weight = self.get_conversion_weight(word, from_lang, to_lang)
        return weight >= threshold
    
    def get_stats(self):
        """Возвращает статистику"""
        return {
            'total_words': len(self.data['words']),
            'total_corrections': self.data['stats']['total_corrections'],
            'protected_words': sum(1 for w in self.data['words'].values() 
                                  if w['weight'] >= self.data['settings']['min_weight']),
            'min_weight': self.data['settings']['min_weight'],
            'max_words': self.data['settings']['max_words']
        }
    
    def get_top_words(self, n=10):
        """Возвращает топ N слов по весу"""
        sorted_words = sorted(
            self.data['words'].items(),
            key=lambda x: x[1]['weight'],
            reverse=True
        )
        return sorted_words[:n]


if __name__ == '__main__':
    # Тестирование
    ud = UserDictionary()
    
    print("📚 Тестирование UserDictionary")
    print("=" * 60)
    
    # Добавляем тестовые слова
    test_words = [
        ('вышел', 'ru'),
        ('логику', 'ru'),
        ('вышел', 'ru'),  # Повторно
        ('сделать', 'ru'),
        ('вышел', 'ru'),  # Ещё раз
    ]
    
    for word, lang in test_words:
        ud.add_correction(word, lang, debug=True)
    
    print()
    print("=" * 60)
    print("📊 Статистика:")
    stats = ud.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print()
    print("🏆 Топ слов:")
    for word, data in ud.get_top_words(5):
        print(f"  {word:15} вес={data['weight']} lang={data['lang']}")
    
    print()
    print("=" * 60)
    print("🔒 Проверка защиты:")
    for word in ['вышел', 'логику', 'неизвестное']:
        protected, weight = ud.is_protected(word, 'ru')
        status = '✅ Защищено' if protected else '❌ Не защищено'
        print(f"  {status} '{word}' (вес: {weight})")
