#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пользовательский словарь для LSwitch - UNIFIED VERSION
Единый словарь с симметричными весами:
  weight > 0: правильная форма = EN
  weight < 0: правильная форма = RU
  weight = 0: удалить запись
"""

import json
import os
import time
from datetime import datetime


class UserDictionary:
    def __init__(self, dict_file=None):
        """
        Инициализация пользовательского словаря
        
        Args:
            dict_file: Путь к файлу словаря
        """
        if dict_file is None:
            config_dir = os.path.expanduser('~/.config/lswitch')
            os.makedirs(config_dir, exist_ok=True)
            dict_file = os.path.join(config_dir, 'user_dict.json')
        
        self.dict_file = dict_file
        
        # Таблица конвертации RU↔EN
        self.ru_to_en = str.maketrans(
            "йцукенгшщзхъфывапролджэячсмитьбюЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ",
            "qwertyuiop[]asdfghjkl;'zxcvbnm,.QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>"
        )
        self.en_to_ru = str.maketrans(
            "qwertyuiop[]asdfghjkl;'zxcvbnm,.QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>",
            "йцукенгшщзхъфывапролджэячсмитьбюЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ"
        )
        
        self.data = self._load()
        
        # Для отложенного сохранения
        self.last_save_time = time.time()
        self.save_interval = 3.0
        self.pending_save = False
    
    def _load(self):
        """Загружает словарь из файла"""
        if os.path.exists(self.dict_file):
            try:
                with open(self.dict_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Миграция старого формата
                    if 'protected' in data or ('conversions' in data and any(':' in k for k in data['conversions'].keys())):
                        print("📦 Миграция словаря на новый формат...")
                        return self._migrate_old_format(data)
                    return data
            except Exception as e:
                print(f"⚠️  Ошибка загрузки user_dict: {e}")
        
        # Новый пустой словарь
        return {
            'conversions': {},
            'settings': {
                'auto_convert_threshold': 5,
                'learning_step': 1,
                'correction_penalty': 1
            },
            'stats': {
                'total_conversions': 0,
                'total_corrections': 0
            }
        }
    
    def _migrate_old_format(self, old_data):
        """Миграция старого формата"""
        new_data = {
            'conversions': {},
            'settings': {
                'auto_convert_threshold': 5,
                'learning_step': 1,
                'correction_penalty': 1
            },
            'stats': {
                'total_conversions': 0,
                'total_corrections': 0
            }
        }
        
        migrated = 0
        
        # Миграция conversions["word:en->ru"]
        if 'conversions' in old_data:
            for key, val in old_data['conversions'].items():
                if ':' not in key:
                    continue
                    
                parts = key.split(':')
                word = parts[0]
                direction = parts[1] if len(parts) > 1 else 'en->ru'
                
                if '->' in direction:
                    from_lang, to_lang = direction.split('->')
                    
                    # Канонизируем в EN
                    canonical = word.lower() if from_lang == 'en' else self._convert_text(word, 'ru', 'en').lower()
                    
                    # Определяем знак веса
                    old_weight = val.get('weight', 0)
                    if from_lang == 'en':
                        weight = old_weight  # Положительный
                    else:
                        weight = -old_weight  # Отрицательный
                    
                    if canonical not in new_data['conversions']:
                        new_data['conversions'][canonical] = {
                            'weight': weight,
                            'last_seen': val.get('last_seen', datetime.now().isoformat())
                        }
                        migrated += 1
                    else:
                        # Суммируем веса
                        new_data['conversions'][canonical]['weight'] += weight
        
        print(f"✅ Мигрировано {migrated} записей")
        return new_data
    
    def _save(self):
        """Отложенное сохранение"""
        current_time = time.time()
        
        if current_time - self.last_save_time >= self.save_interval:
            self._do_save()
            self.last_save_time = current_time
            self.pending_save = False
        else:
            self.pending_save = True
    
    def _do_save(self):
        """Реальное сохранение в файл"""
        try:
            with open(self.dict_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  Ошибка сохранения user_dict: {e}")
    
    def flush(self):
        """Принудительное сохранение"""
        if self.pending_save:
            self._do_save()
            self.pending_save = False
    
    def _detect_lang(self, text):
        """Определяет язык текста по содержимому"""
        has_cyrillic = any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in text)
        return 'ru' if has_cyrillic else 'en'
    
    def _convert_text(self, text, from_lang, to_lang):
        """Конвертирует текст между раскладками"""
        if from_lang == to_lang:
            return text
        if from_lang == 'ru' and to_lang == 'en':
            return text.translate(self.ru_to_en)
        if from_lang == 'en' and to_lang == 'ru':
            return text.translate(self.en_to_ru)
        return text
    
    def _canonicalize(self, text, current_lang):
        """Канонизация: всегда EN в lowercase"""
        if current_lang == 'en':
            return text.lower()
        return self._convert_text(text, 'ru', 'en').lower()
    
    # ========== ПУБЛИЧНЫЕ МЕТОДЫ ==========
    
    def should_auto_convert(self, text, from_lang, to_lang, threshold=None):
        """
        Проверяет нужна ли автоконвертация
        
        Args:
            text: Текст для проверки
            from_lang: Текущий язык текста ('ru' или 'en')
            to_lang: Целевой язык (не используется в новой логике)
            threshold: Порог автоконвертации (из конфига если None)
        
        Returns:
            bool: True если нужна автоконвертация
        """
        if threshold is None:
            threshold = self.data['settings']['auto_convert_threshold']
        
        # Канонизируем текст
        canonical = self._canonicalize(text, from_lang)
        
        if canonical not in self.data['conversions']:
            return False
        
        weight = self.data['conversions'][canonical]['weight']
        
        # Логика автоконвертации:
        # from_lang='ru', weight > 0 → конвертировать еуые→test
        # from_lang='en', weight < 0 → конвертировать test→еуые
        if from_lang == 'ru' and weight >= threshold:
            return True
        if from_lang == 'en' and weight <= -threshold:
            return True
        
        return False
    
    def add_conversion(self, word, from_lang, to_lang, debug=False):
        """
        Добавляет успешную ручную конвертацию
        
        Args:
            word: Исходное слово (ДО конвертации)
            from_lang: Язык исходного слова
            to_lang: Целевой язык
            debug: Вывод отладки
        """
        canonical = self._canonicalize(word, from_lang)
        learning_step = self.data['settings']['learning_step']
        
        if canonical not in self.data['conversions']:
            self.data['conversions'][canonical] = {
                'weight': 0,
                'last_seen': datetime.now().isoformat()
            }
        
        # Увеличиваем/уменьшаем вес в зависимости от направления
        if from_lang == 'ru' and to_lang == 'en':
            # ru→en: увеличиваем вес (сдвиг к EN)
            self.data['conversions'][canonical]['weight'] += learning_step
        elif from_lang == 'en' and to_lang == 'ru':
            # en→ru: уменьшаем вес (сдвиг к RU)
            self.data['conversions'][canonical]['weight'] -= learning_step
        
        self.data['conversions'][canonical]['last_seen'] = datetime.now().isoformat()
        self.data['stats']['total_conversions'] += 1
        
        if debug:
            weight = self.data['conversions'][canonical]['weight']
            print(f"📚 Conversion: '{word}' ({from_lang}→{to_lang}) вес → {weight}")
        
        # Очистка при weight=0
        if self.data['conversions'][canonical]['weight'] == 0:
            del self.data['conversions'][canonical]
            if debug:
                print(f"📚 Удалено: '{canonical}' (вес = 0)")
        
        self._save()
    
    def add_correction(self, word, lang, debug=False):
        """
        Коррекция автоконвертации (пользователь вернул обратно)
        
        Args:
            word: ИСХОДНОЕ слово (до автоконвертации)
            lang: Язык исходного слова
            debug: Отладка
        """
        canonical = self._canonicalize(word, lang)
        penalty = self.data['settings']['correction_penalty']
        
        if canonical not in self.data['conversions']:
            # Создаем запись с отрицательным весом
            self.data['conversions'][canonical] = {
                'weight': -penalty if lang == 'ru' else penalty,
                'last_seen': datetime.now().isoformat()
            }
        else:
            old_weight = self.data['conversions'][canonical]['weight']
            
            # Коррекция: двигаем вес в ПРОТИВОПОЛОЖНУЮ сторону
            if lang == 'ru':
                # Было автоконвертировано еуые→test, исправили обратно
                # Уменьшаем вес (сдвиг к RU)
                self.data['conversions'][canonical]['weight'] -= penalty
            else:
                # Было автоконвертировано test→еуые, исправили обратно
                # Увеличиваем вес (сдвиг к EN)
                self.data['conversions'][canonical]['weight'] += penalty
            
            new_weight = self.data['conversions'][canonical]['weight']
            
            if debug:
                print(f"📚 Correction: '{word}' ({lang}) вес {old_weight} → {new_weight}")
            
            # Удаляем если вес стал 0
            if new_weight == 0:
                del self.data['conversions'][canonical]
                if debug:
                    print(f"📚 Удалено: '{canonical}' (вес = 0)")
        
        self.data['stats']['total_corrections'] += 1
        self._save()
    
    def get_conversion_weight(self, word, from_lang, to_lang):
        """
        Получает вес конвертации (для совместимости)
        
        Returns:
            int: абсолютное значение веса
        """
        canonical = self._canonicalize(word, from_lang)
        
        if canonical not in self.data['conversions']:
            return 0
        
        weight = self.data['conversions'][canonical]['weight']
        
        # Возвращаем абсолютное значение для проверки порога
        if from_lang == 'ru':
            return weight if weight > 0 else 0
        else:
            return abs(weight) if weight < 0 else 0
    
    def is_protected(self, word, lang):
        """
        Заглушка для обратной совместимости
        Теперь защита определяется автоматически через вес
        
        Returns:
            (False, 0): всегда, защиты больше нет
        """
        return (False, 0)
    
    def get_stats(self):
        """Возвращает статистику"""
        return {
            'total_words': len(self.data['conversions']),
            'total_conversions': self.data['stats']['total_conversions'],
            'total_corrections': self.data['stats']['total_corrections'],
            'avg_weight': sum(abs(v['weight']) for v in self.data['conversions'].values()) / len(self.data['conversions']) if self.data['conversions'] else 0
        }
