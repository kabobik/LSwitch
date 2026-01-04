#!/usr/bin/env python3
"""
Тесты для LSwitch
"""

import unittest
import sys
import os

# Добавляем путь к модулю
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lswitch import EN_TO_RU, RU_TO_EN, LSwitch


class TestLayoutMapping(unittest.TestCase):
    """Тесты маппинга раскладок"""
    
    def test_en_to_ru_basic(self):
        """Базовые символы EN -> RU"""
        self.assertEqual(EN_TO_RU['q'], 'й')
        self.assertEqual(EN_TO_RU['w'], 'ц')
        self.assertEqual(EN_TO_RU['a'], 'ф')
        
    def test_ru_to_en_basic(self):
        """Базовые символы RU -> EN"""
        self.assertEqual(RU_TO_EN['й'], 'q')
        self.assertEqual(RU_TO_EN['ц'], 'w')
        self.assertEqual(RU_TO_EN['ф'], 'a')
    
    def test_uppercase(self):
        """Заглавные буквы"""
        self.assertEqual(EN_TO_RU['Q'], 'Й')
        self.assertEqual(RU_TO_EN['Й'], 'Q')
    
    def test_special_chars(self):
        """Спецсимволы"""
        self.assertEqual(EN_TO_RU['<'], 'Б')  # Shift+запятая
        self.assertEqual(EN_TO_RU['>'], 'Ю')  # Shift+точка
        self.assertEqual(RU_TO_EN['Б'], '<')
        self.assertEqual(RU_TO_EN['Ю'], '>')


class TestConversion(unittest.TestCase):
    """Тесты конвертации текста"""
    
    def setUp(self):
        """Создаём экземпляр LSwitch для тестов"""
        self.app = LSwitch()
    
    def test_en_to_ru_word(self):
        """Конвертация слова EN -> RU"""
        result = self.app.convert_text('ghbdtn')
        self.assertEqual(result, 'привет')
    
    def test_ru_to_en_word(self):
        """Конвертация слова RU -> EN"""
        result = self.app.convert_text('привет')
        self.assertEqual(result, 'ghbdtn')
    
    def test_en_to_ru_uppercase(self):
        """Конвертация с заглавными"""
        result = self.app.convert_text('Ghbdtn')
        self.assertEqual(result, 'Привет')
    
    def test_mixed_with_punctuation(self):
        """Конвертация с пунктуацией"""
        result = self.app.convert_text('ghbdtn,')
        self.assertEqual(result, 'привет,')  # Запятая остается
        
        result2 = self.app.convert_text('hello.')
        self.assertEqual(result2, 'руддщ.')  # Точка остается
    
    def test_empty_string(self):
        """Пустая строка"""
        result = self.app.convert_text('')
        self.assertEqual(result, '')
    
    def test_complex_phrase(self):
        """Сложная фраза"""
        result = self.app.convert_text('ghbdtn vbh')
        self.assertEqual(result, 'привет мир')
    
    def test_numbers_preserved(self):
        """Цифры сохраняются"""
        result = self.app.convert_text('ntcn123')
        self.assertEqual(result, 'тест123')


class TestBuffer(unittest.TestCase):
    """Тесты буфера ввода"""
    
    def setUp(self):
        """Создаём экземпляр LSwitch для тестов"""
        self.app = LSwitch()
    
    def test_add_to_buffer(self):
        """Добавление в буфер"""
        self.app.add_to_buffer('a')
        self.app.add_to_buffer('b')
        self.app.add_to_buffer('c')
        self.assertEqual(self.app.input_buffer, ['a', 'b', 'c'])
    
    def test_get_last_word_simple(self):
        """Получение последнего слова"""
        self.app.input_buffer = ['h', 'e', 'l', 'l', 'o']
        word = self.app.get_last_word_from_buffer()
        self.assertEqual(word, 'hello')
    
    def test_get_last_word_with_space(self):
        """Получение последнего слова после пробела"""
        self.app.input_buffer = ['h', 'e', 'l', 'l', 'o', ' ', 'w', 'o', 'r', 'l', 'd']
        word = self.app.get_last_word_from_buffer()
        self.assertEqual(word, 'world')
    
    def test_get_last_word_empty(self):
        """Пустой буфер"""
        self.app.input_buffer = []
        word = self.app.get_last_word_from_buffer()
        self.assertIsNone(word)
    
    def test_get_last_word_only_spaces(self):
        """Только пробелы"""
        self.app.input_buffer = [' ', ' ', ' ']
        word = self.app.get_last_word_from_buffer()
        self.assertIsNone(word)
    
    def test_buffer_size_limit(self):
        """Ограничение размера буфера"""
        # Добавляем больше чем buffer_max_size
        for i in range(150):
            self.app.add_to_buffer(str(i % 10))
        
        # Буфер не должен превышать максимум
        self.assertLessEqual(len(self.app.input_buffer), self.app.buffer_max_size)
    
    def test_clear_buffer(self):
        """Очистка буфера"""
        self.app.input_buffer = ['a', 'b', 'c']
        self.app.clear_buffer()
        self.assertEqual(self.app.input_buffer, [])


class TestRussianWords(unittest.TestCase):
    """Тесты с реальными русскими словами"""
    
    def setUp(self):
        self.app = LSwitch()
    
    def test_common_words(self):
        """Частые слова"""
        test_cases = [
            ('ntcn', 'тест'),
            ('ghbdtn', 'привет'),
            ('vbh', 'мир'),
            ('ckjdj', 'слово'),
            ('ntrcn', 'текст'),
        ]
        
        for en_text, ru_expected in test_cases:
            with self.subTest(en_text=en_text):
                result = self.app.convert_text(en_text)
                self.assertEqual(result, ru_expected)
    
    def test_reverse_common_words(self):
        """Обратная конвертация частых слов"""
        test_cases = [
            ('тест', 'ntcn'),
            ('привет', 'ghbdtn'),
            ('мир', 'vbh'),
            ('слово', 'ckjdj'),
        ]
        
        for ru_text, en_expected in test_cases:
            with self.subTest(ru_text=ru_text):
                result = self.app.convert_text(ru_text)
                self.assertEqual(result, en_expected)


class TestEdgeCases(unittest.TestCase):
    """Граничные случаи"""
    
    def setUp(self):
        self.app = LSwitch()
    
    def test_single_char(self):
        """Один символ"""
        self.assertEqual(self.app.convert_text('q'), 'й')
        self.assertEqual(self.app.convert_text('й'), 'q')
    
    def test_very_long_word(self):
        """Очень длинное слово"""
        long_word = 'qwertyuiopasdfghjkl;'  # Добавлена точка с запятой для ж
        result = self.app.convert_text(long_word)
        self.assertEqual(result, 'йцукенгшщзфывапролдж')
    
    def test_mixed_layouts(self):
        """Смешанные раскладки (должна определяться по большинству)"""
        # Больше английских символов - конвертируем в русский
        result = self.app.convert_text('hello')
        self.assertEqual(result, 'руддщ')
        
        # Больше русских символов - конвертируем в английский
        result2 = self.app.convert_text('привет')
        self.assertEqual(result2, 'ghbdtn')


def run_tests():
    """Запуск всех тестов"""
    # Создаём test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Добавляем все тесты
    suite.addTests(loader.loadTestsFromTestCase(TestLayoutMapping))
    suite.addTests(loader.loadTestsFromTestCase(TestConversion))
    suite.addTests(loader.loadTestsFromTestCase(TestBuffer))
    suite.addTests(loader.loadTestsFromTestCase(TestRussianWords))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    # Запускаем
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Возвращаем код выхода
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
