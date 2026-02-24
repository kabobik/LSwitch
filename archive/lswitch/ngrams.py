#!/usr/bin/env python3
"""
N-граммы для оценки естественности текста
Частоты собраны из корпусов текстов
"""

# Частые биграммы русского языка (топ-200)
BIGRAMS_RU = {
    'пр': 850, 'ст': 820, 'ра': 800, 'то': 780, 'ов': 750, 'на': 740, 'ен': 720, 'ко': 700,
    'не': 680, 'те': 660, 'ро': 640, 'ре': 620, 'ни': 600, 'та': 580, 'по': 560, 'ва': 540,
    'ом': 520, 'ор': 500, 'ли': 480, 'ка': 460, 'ет': 440, 'ла': 420, 'го': 400, 'ть': 380,
    'ри': 360, 'но': 340, 'ый': 320, 'ог': 300, 'од': 280, 'ер': 260, 'ле': 240, 'ит': 220,
    'ос': 200, 'ав': 190, 'ес': 180, 'ло': 170, 'се': 160, 'ме': 150, 'де': 140, 'ны': 130,
    'во': 125, 'са': 120, 'ве': 115, 'ед': 110, 'да': 105, 'со': 100, 'об': 95, 'ма': 90,
    'ол': 88, 'ас': 86, 'ис': 84, 'ан': 82, 'ел': 80, 'ем': 78, 'ми': 76, 'тв': 74,
    'от': 72, 'ал': 70, 'ез': 68, 'ак': 66, 'ое': 64, 'ск': 62, 'ир': 60, 'ик': 58,
    'им': 56, 'ия': 54, 'ый': 52, 'ил': 50, 'ки': 48, 'ам': 46, 'уд': 44, 'бо': 42,
    'вы': 40, 'яз': 38, 'че': 36, 'мо': 34, 'до': 32, 'сл': 30, 'ша': 28, 'жи': 26,
}

# Частые триграммы русского языка (топ-100)
TRIGRAMS_RU = {
    'ств': 500, 'ово': 480, 'ени': 460, 'тор': 440, 'при': 420, 'ого': 400, 'ова': 380,
    'ени': 360, 'ост': 340, 'ков': 320, 'про': 300, 'пре': 280, 'ние': 260, 'ром': 240,
    'тел': 220, 'ель': 200, 'ера': 190, 'ста': 180, 'вер': 170, 'лен': 160, 'рав': 150,
    'вор': 140, 'над': 130, 'раз': 120, 'под': 110, 'пол': 100, 'вол': 95, 'мен': 90,
    'чел': 85, 'век': 80, 'жен': 75, 'тво': 70, 'сто': 65, 'точ': 60, 'род': 55,
    'ден': 50, 'год': 48, 'дел': 46, 'нос': 44, 'ран': 42, 'руб': 40, 'тер': 38,
}

# Запрещённые комбинации в русском
FORBIDDEN_RU = {
    'жы': -1000, 'шы': -1000, 'чя': -1000, 'щя': -1000, 'жю': -1000, 'шю': -1000, 'чю': -1000,
    'йй': -800, 'ьь': -800, 'ъъ': -800, 'ыь': -500, 'ьы': -500, 'ъь': -500, 'ьъ': -500,
}

# Частые биграммы английского языка (топ-200)
BIGRAMS_EN = {
    'th': 900, 'he': 880, 'in': 860, 'er': 840, 'an': 820, 're': 800, 'on': 780, 'at': 760,
    'en': 740, 'nd': 720, 'ti': 700, 'es': 680, 'or': 660, 'te': 640, 'of': 620, 'ed': 600,
    'is': 580, 'it': 560, 'al': 540, 'ar': 520, 'st': 500, 'to': 480, 'nt': 460, 'ng': 440,
    'se': 420, 'ha': 400, 'as': 380, 'ou': 360, 'io': 340, 'le': 320, 've': 300, 'co': 280,
    'me': 260, 'de': 240, 'hi': 220, 'ri': 200, 'ro': 190, 'ic': 180, 'ne': 170, 'ea': 160,
    'ra': 150, 'ce': 140, 'll': 135, 'so': 130, 'si': 125, 'la': 120, 'el': 115, 'ma': 110,
    'di': 105, 'fo': 100, 'ca': 98, 'ot': 96, 'no': 94, 'rs': 92, 'us': 90, 'li': 88,
    'ho': 86, 'ur': 84, 'et': 82, 'ut': 80, 'rt': 78, 'om': 76, 'ta': 74, 'ec': 72,
}

# Частые триграммы английского языка (топ-100)
TRIGRAMS_EN = {
    'the': 800, 'and': 750, 'ing': 700, 'ion': 650, 'tio': 600, 'ent': 550, 'ati': 500,
    'for': 480, 'her': 460, 'ter': 440, 'hat': 420, 'tha': 400, 'ere': 380, 'ate': 360,
    'his': 340, 'con': 320, 'res': 300, 'ver': 280, 'all': 260, 'ons': 240, 'nce': 220,
    'men': 200, 'ith': 190, 'ted': 180, 'ers': 170, 'pro': 160, 'thi': 150, 'wit': 140,
    'are': 130, 'ess': 120, 'not': 110, 'ive': 100, 'was': 95, 'ect': 90, 'rea': 85,
}

def calculate_ngram_score(text, lang='ru'):
    """
    Вычисляет "естественность" текста на основе частот n-грамм
    Чем выше score, тем больше текст похож на настоящий язык
    """
    # Фильтруем только буквы (убираем спецсимволы, цифры, пробелы)
    text_clean = ''.join(c for c in text if c.isalpha())
    
    if not text_clean or len(text_clean) < 2:
        return -100  # Слишком короткий или нет букв - очень низкий score
    
    text_clean = text_clean.lower()
    score = 0
    
    # Выбираем словари для языка
    if lang == 'ru':
        bigrams = BIGRAMS_RU
        trigrams = TRIGRAMS_RU
        forbidden = FORBIDDEN_RU
    else:  # en
        bigrams = BIGRAMS_EN
        trigrams = TRIGRAMS_EN
        forbidden = {}
    
    # Проверяем запрещённые комбинации (высокий штраф)
    for forbidden_seq, penalty in forbidden.items():
        if forbidden_seq in text_clean:
            score += penalty * text_clean.count(forbidden_seq)
    
    # Оцениваем триграммы (вес 3)
    for i in range(len(text_clean) - 2):
        trigram = text_clean[i:i+3]
        score += trigrams.get(trigram, -5) * 3
    
    # Оцениваем биграммы (вес 1)
    for i in range(len(text_clean) - 1):
        bigram = text_clean[i:i+2]
        score += bigrams.get(bigram, -2)
    
    # Нормализуем на длину ОТФИЛЬТРОВАННОГО текста
    if len(text_clean) > 0:
        score = score / len(text_clean)
    
    return score

def evaluate_text_variants(text):
    """
    Оценивает все варианты конвертации текста и возвращает лучший
    
    Возвращает: (best_text, conversion_type, score_original, score_best)
    """
    from lswitch.dictionary import EN_TO_RU, RU_TO_EN
    
    # 1. Определяем текущий язык текста
    has_cyrillic = any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in text)
    has_latin = any('a' <= c.lower() <= 'z' for c in text)
    
    if has_cyrillic:
        current_lang = 'ru'
    elif has_latin:
        current_lang = 'en'
    else:
        return (text, 'unknown', 0, 0)
    
    # 2. Считаем score для оригинала
    score_original = calculate_ngram_score(text, current_lang)
    
    # 3. Генерируем варианты конвертации
    variants = [(text, 'original', score_original, current_lang)]
    
    if current_lang == 'en':
        # Попробуем EN → RU
        ru_variant = text.translate(EN_TO_RU)
        score_ru = calculate_ngram_score(ru_variant, 'ru')
        variants.append((ru_variant, 'en_to_ru', score_ru, 'ru'))
    
    elif current_lang == 'ru':
        # Попробуем RU → EN
        en_variant = text.translate(RU_TO_EN)
        score_en = calculate_ngram_score(en_variant, 'en')
        variants.append((en_variant, 'ru_to_en', score_en, 'en'))
    
    # 4. Выбираем вариант с максимальным score
    best = max(variants, key=lambda x: x[2])
    
    return (best[0], best[1], score_original, best[2])

def should_convert(text, threshold=10, user_dict=None):
    """
    Определяет нужно ли конвертировать текст
    
    ПРИОРИТЕТЫ (от высшего к низшему):
    1. Слово в текущем словаре → НЕ трогаем
    1.5. Слово в user_dict (самообучающийся) → НЕ трогаем
    2. Слово НЕ в текущем, но конвертированное В целевом словаре → КОНВЕРТИРУЕМ
    3. N-gram анализ (fallback)
    
    Возвращает: (should_convert: bool, best_text: str, reason: str)
    """
    from lswitch.dictionary import RUSSIAN_WORDS, ENGLISH_WORDS, EN_TO_RU, RU_TO_EN
    
    # Определяем текущий язык
    has_cyrillic = any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in text)
    current_lang = 'ru' if has_cyrillic else 'en'
    other_lang = 'en' if current_lang == 'ru' else 'ru'
    
    # Приоритет 1: Проверяем в ТЕКУЩЕМ словаре
    text_lower = text.lower()
    if current_lang == 'ru' and text_lower in RUSSIAN_WORDS:
        return (False, text, f"found_in_RU_dictionary (PRIORITY 1: original valid)")
    elif current_lang == 'en' and text_lower in ENGLISH_WORDS:
        return (False, text, f"found_in_EN_dictionary (PRIORITY 1: original valid)")
    
    # Приоритет 1.5: Проверяем в пользовательском словаре (самообучение)
    if user_dict:
        protected, weight = user_dict.is_protected(text_lower, current_lang)
        if protected:
            return (False, text, f"user_dict_protected (вес: {weight}, PRIORITY 1.5: user learned)")
    
    # Приоритет 2: Конвертируем и проверяем в ЦЕЛЕВОМ словаре
    if current_lang == 'en':
        converted = text.translate(EN_TO_RU)
    else:
        converted = text.translate(RU_TO_EN)
    
    converted_lower = converted.lower()
    if other_lang == 'ru' and converted_lower in RUSSIAN_WORDS:
        return (True, converted, f"not_in_EN + found_in_RU_dict (PRIORITY 2: dict conversion)")
    elif other_lang == 'en' and converted_lower in ENGLISH_WORDS:
        return (True, converted, f"not_in_RU + found_in_EN_dict (PRIORITY 2: dict conversion)")
    
    # Приоритет 3: Проверка спецсимволов (защита паролей)
    special_chars = set('!@#$%^&*()_+-=[]{}|;:,.<>?/~`"\'\\\t\n')
    has_special_orig = any(c in special_chars for c in text)
    has_special_conv = any(c in special_chars for c in converted)
    
    # Если спецсимволы остаются после конвертации - скорее всего пароль
    if has_special_orig and has_special_conv:
        return (False, text, "special_chars_both (password protection)")
    
    # Приоритет 4: N-gram анализ (fallback для слов вне словаря)
    best_text, conversion_type, score_orig, score_best = evaluate_text_variants(text)
    
    # Если это оригинал - не конвертируем
    if conversion_type == 'original':
        return (False, text, f"original_best (score: {score_orig:.1f})")
    
    # Вычисляем разницу
    score_diff = score_best - score_orig
    
    # Если улучшение незначительное - не трогаем
    if score_diff < threshold:
        # Но если оба score очень низкие (< 0), проверяем словарь
        if score_orig < 0 and score_best < 0:
            try:
                from lswitch.dictionary import check_word
                
                # Проверяем оригинал и конвертированный в словаре
                is_orig_valid, _ = check_word(text, 'en' if conversion_type == 'en_to_ru' else 'ru')
                is_conv_valid, _ = check_word(best_text, 'ru' if conversion_type == 'en_to_ru' else 'en')
                
                # Если оригинал НЕ в словаре, а конвертированный В словаре - конвертируем
                if not is_orig_valid and is_conv_valid:
                    return (True, best_text, f"{conversion_type} (dictionary fallback)")
            except:
                pass
        
        return (False, text, f"diff_too_small ({score_diff:.1f} < {threshold})")
    
    # Если улучшение значительное - конвертируем
    return (True, best_text, f"{conversion_type} (gain: {score_diff:.1f})")

if __name__ == '__main__':
    # Тесты
    test_cases = [
        "ghbdtn rfr ltkf",  # привет как дела (набрано на EN)
        "привет как дела",   # правильный русский
        "ghbdtn",            # привет
        "hello world",       # правильный английский
        "руддщ цщкдв",       # hello world (набрано на RU)
    ]
    
    print("🧪 Тестирование n-граммного анализа:\n")
    for text in test_cases:
        should_conv, result, reason = should_convert(text, threshold=5)
        print(f"Текст: '{text}'")
        print(f"  → Результат: '{result}'")
        print(f"  → Конвертировать: {'✓ ДА' if should_conv else '✗ НЕТ'}")
        print(f"  → Причина: {reason}\n")
