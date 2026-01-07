#!/usr/bin/env python3
"""
Словари для автопереключения раскладки
Содержит частые слова для определения правильной раскладки
"""

# Топ-1000 частых русских слов
RUSSIAN_WORDS = {
    'а', 'в', 'и', 'на', 'не', 'с', 'что', 'как', 'по', 'за', 'из', 'от', 'к', 'у', 'о', 'для',
    'это', 'он', 'она', 'они', 'мы', 'вы', 'ты', 'я',
    'все', 'весь', 'всё', 'быть', 'был', 'была', 'было', 'были', 'есть', 'если', 'его', 'её', 'их',
    'или', 'да', 'нет', 'но', 'так', 'же', 'уже', 'еще', 'ещё', 'тоже', 'только', 'очень',
    'может', 'можно', 'надо', 'нужно', 'должен', 'должна', 'должно', 'должны',
    'год', 'время', 'раз', 'день', 'жизнь', 'человек', 'дело', 'место', 'слово', 'работа',
    'который', 'которая', 'которое', 'которые', 'свой', 'своя', 'своё', 'свои',
    'один', 'одна', 'одно', 'два', 'три', 'четыре', 'пять', 'много', 'мало', 'больше', 'меньше',
    'хорошо', 'плохо', 'новый', 'старый', 'большой', 'маленький', 'первый', 'последний',
    'сказать', 'говорить', 'делать', 'знать', 'думать', 'видеть', 'хотеть', 'дать', 'взять',
    'стать', 'сделать', 'пойти', 'идти', 'прийти', 'выйти', 'войти', 'сидеть', 'стоять',
    'сейчас', 'теперь', 'тогда', 'потом', 'здесь', 'там', 'где', 'куда', 'когда', 'почему',
    'зачем', 'откуда', 'сколько', 'какой', 'какая', 'какое', 'какие', 'чей', 'чья', 'чьё', 'чьи',
    'этот', 'эта', 'это', 'эти', 'тот', 'та', 'те',
    'другой', 'другая', 'другое', 'другие', 'такой', 'такая', 'такое', 'такие',
    'привет', 'пока', 'спасибо', 'пожалуйста', 'здравствуйте', 'до', 'свидания',
    'добрый', 'утро', 'вечер', 'ночь', 'день',
    'дом', 'квартира', 'город', 'страна', 'мир', 'земля', 'вода', 'огонь', 'воздух',
    'рука', 'нога', 'голова', 'глаз', 'ухо', 'нос', 'рот', 'сердце', 'душа', 'тело',
    'мать', 'отец', 'сын', 'дочь', 'брат', 'сестра', 'друг', 'друзья', 'семья', 'родители',
    'вопрос', 'ответ', 'проблема', 'решение', 'задача', 'цель', 'путь', 'способ', 'результат',
    'начало', 'конец', 'середина', 'часть', 'целое', 'сторона', 'край', 'центр',
    'право', 'левый', 'правый', 'верх', 'низ', 'высоко', 'низко', 'далеко', 'близко',
    'книга', 'текст', 'страница', 'письмо', 'слово', 'предложение', 'буква', 'цифра', 'число',
    'школа', 'университет', 'учитель', 'ученик', 'студент', 'урок', 'лекция', 'экзамен',
    'компьютер', 'телефон', 'интернет', 'сайт', 'программа', 'файл', 'папка', 'данные',
    'работать', 'учиться', 'играть', 'читать', 'писать', 'слушать', 'смотреть', 'понимать',
    'любить', 'нравиться', 'хотеть', 'мочь', 'уметь', 'знать', 'помнить', 'забыть',
    'начать', 'начинать', 'кончить', 'кончать', 'продолжать', 'продолжить', 'остановить',
    'хороший', 'плохой', 'красивый', 'некрасивый', 'умный', 'глупый', 'добрый', 'злой',
    'правда', 'ложь', 'истина', 'правильно', 'неправильно', 'верно', 'неверно',
    'важный', 'главный', 'нужный', 'необходимый', 'интересный', 'скучный', 'трудный', 'легкий',
    'случай', 'история', 'событие', 'факт', 'пример', 'причина', 'следствие', 'вывод',
    'мнение', 'точка', 'зрения', 'взгляд', 'позиция', 'отношение', 'чувство', 'эмоция',
    'радость', 'грусть', 'счастье', 'горе', 'страх', 'надежда', 'вера', 'любовь', 'ненависть',
    'утро', 'день', 'вечер', 'ночь', 'рассвет', 'закат', 'солнце', 'луна', 'звезда', 'небо',
    'погода', 'дождь', 'снег', 'ветер', 'холод', 'тепло', 'жара', 'мороз', 'лето', 'зима',
    'весна', 'осень', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август',
    'сентябрь', 'октябрь', 'ноябрь', 'декабрь', 'неделя', 'месяц', 'понедельник', 'вторник',
    'среда', 'четверг', 'пятница', 'суббота', 'воскресенье', 'сегодня', 'вчера', 'завтра',
}

# Карты конвертации для быстрого преобразования
_EN_TO_RU_MAP = {
    'q': 'й', 'w': 'ц', 'e': 'у', 'r': 'к', 't': 'е', 'y': 'н', 'u': 'г', 'i': 'ш', 'o': 'щ', 'p': 'з',
    '[': 'х', ']': 'ъ', 'a': 'ф', 's': 'ы', 'd': 'в', 'f': 'а', 'g': 'п', 'h': 'р', 'j': 'о', 'k': 'л',
    'l': 'д', ';': 'ж', "'": 'э', 'z': 'я', 'x': 'ч', 'c': 'с', 'v': 'м', 'b': 'и', 'n': 'т', 'm': 'ь',
    ',': 'б', '.': 'ю', '/': '.', '`': 'ё',
}
_RU_TO_EN_MAP = {v: k for k, v in _EN_TO_RU_MAP.items()}

# Топ-1000 частых английских слов
ENGLISH_WORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'if', 'then', 'else', 'when', 'at', 'by', 'for', 'from',
    'in', 'on', 'to', 'with', 'of', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
    'my', 'your', 'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs',
    'this', 'that', 'these', 'those', 'who', 'what', 'where', 'when', 'why', 'how', 'which',
    'all', 'some', 'any', 'many', 'much', 'few', 'little', 'more', 'most', 'other', 'another',
    'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'first', 'second',
    'no', 'not', 'yes', 'can', 'could', 'will', 'would', 'shall', 'should', 'may', 'might', 'must',
    'do', 'does', 'did', 'done', 'doing', 'have', 'has', 'had', 'having', 'get', 'got', 'getting',
    'make', 'made', 'making', 'go', 'went', 'gone', 'going', 'come', 'came', 'coming', 'see', 'saw',
    'seen', 'seeing', 'know', 'knew', 'known', 'knowing', 'think', 'thought', 'thinking', 'take',
    'took', 'taken', 'taking', 'want', 'wanted', 'wanting', 'give', 'gave', 'given', 'giving',
    'use', 'used', 'using', 'find', 'found', 'finding', 'tell', 'told', 'telling', 'ask', 'asked',
    'work', 'worked', 'working', 'call', 'called', 'calling', 'try', 'tried', 'trying', 'need',
    'feel', 'felt', 'feeling', 'become', 'became', 'becoming', 'leave', 'left', 'leaving', 'put',
    'mean', 'meant', 'meaning', 'keep', 'kept', 'keeping', 'let', 'begin', 'began', 'beginning',
    'seem', 'seemed', 'seeming', 'help', 'helped', 'helping', 'show', 'showed', 'showing', 'hear',
    'heard', 'hearing', 'play', 'played', 'playing', 'run', 'ran', 'running', 'move', 'moved',
    'live', 'lived', 'living', 'believe', 'believed', 'believing', 'bring', 'brought', 'bringing',
    'happen', 'happened', 'happening', 'write', 'wrote', 'written', 'writing', 'sit', 'sat',
    'stand', 'stood', 'standing', 'lose', 'lost', 'losing', 'pay', 'paid', 'paying', 'meet', 'met',
    'include', 'included', 'including', 'continue', 'continued', 'continuing', 'set', 'learn',
    'change', 'changed', 'changing', 'lead', 'led', 'leading', 'understand', 'understood',
    'watch', 'watched', 'watching', 'follow', 'followed', 'following', 'stop', 'stopped', 'stopping',
    'create', 'created', 'creating', 'speak', 'spoke', 'spoken', 'speaking', 'read', 'reading',
    'allow', 'allowed', 'allowing', 'add', 'added', 'adding', 'spend', 'spent', 'spending', 'grow',
    'open', 'opened', 'opening', 'walk', 'walked', 'walking', 'win', 'won', 'winning', 'offer',
    'remember', 'remembered', 'remembering', 'love', 'loved', 'loving', 'consider', 'considered',
    'appear', 'appeared', 'appearing', 'buy', 'bought', 'buying', 'wait', 'waited', 'waiting',
    'serve', 'served', 'serving', 'die', 'died', 'dying', 'send', 'sent', 'sending', 'expect',
    'build', 'built', 'building', 'stay', 'stayed', 'staying', 'fall', 'fell', 'fallen', 'falling',
    'cut', 'cutting', 'reach', 'reached', 'reaching', 'kill', 'killed', 'killing', 'raise', 'raised',
    'pass', 'passed', 'passing', 'sell', 'sold', 'selling', 'require', 'required', 'requiring',
    'report', 'reported', 'reporting', 'decide', 'decided', 'deciding', 'pull', 'pulled', 'pulling',
    'time', 'year', 'day', 'week', 'month', 'hour', 'minute', 'second', 'morning', 'afternoon',
    'evening', 'night', 'today', 'yesterday', 'tomorrow', 'monday', 'tuesday', 'wednesday',
    'thursday', 'friday', 'saturday', 'sunday', 'january', 'february', 'march', 'april', 'may',
    'june', 'july', 'august', 'september', 'october', 'november', 'december', 'spring', 'summer',
    'autumn', 'fall', 'winter', 'season', 'century', 'period', 'moment', 'history', 'future', 'past',
    'people', 'person', 'man', 'woman', 'child', 'boy', 'girl', 'friend', 'family', 'mother',
    'father', 'parent', 'son', 'daughter', 'brother', 'sister', 'husband', 'wife', 'baby', 'kid',
    'way', 'place', 'world', 'country', 'city', 'town', 'area', 'home', 'house', 'room', 'street',
    'door', 'window', 'floor', 'wall', 'table', 'chair', 'bed', 'school', 'office', 'court', 'church',
    'thing', 'fact', 'case', 'problem', 'issue', 'question', 'answer', 'reason', 'result', 'change',
    'end', 'point', 'group', 'number', 'part', 'system', 'order', 'form', 'line', 'side', 'level',
    'hand', 'eye', 'head', 'face', 'body', 'heart', 'mind', 'voice', 'foot', 'back', 'arm', 'leg',
    'name', 'word', 'language', 'book', 'letter', 'page', 'story', 'idea', 'information', 'news',
    'money', 'power', 'law', 'right', 'left', 'state', 'government', 'company', 'business', 'service',
    'water', 'food', 'air', 'fire', 'light', 'sound', 'color', 'red', 'blue', 'green', 'white',
    'black', 'car', 'road', 'tree', 'land', 'war', 'game', 'music', 'art', 'program', 'computer',
    'phone', 'internet', 'email', 'website', 'file', 'data', 'image', 'video', 'picture', 'photo',
    'good', 'bad', 'new', 'old', 'great', 'big', 'small', 'long', 'short', 'high', 'low', 'little',
    'young', 'early', 'late', 'important', 'different', 'same', 'large', 'social', 'national', 'own',
    'other', 'right', 'wrong', 'true', 'false', 'real', 'full', 'sure', 'clear', 'hard', 'easy',
    'strong', 'free', 'happy', 'sorry', 'ready', 'simple', 'certain', 'personal', 'open', 'red',
    'best', 'better', 'worse', 'worst', 'main', 'only', 'public', 'able', 'bad', 'possible', 'local',
    'hello', 'hi', 'bye', 'goodbye', 'thanks', 'please', 'sorry', 'welcome', 'okay', 'ok', 'well',
}


# Создаём дополнительные словари: русские слова, набранные на английской раскладке
# Например, "привет" -> "ghbdtn"
def _convert_word(word: str, char_map: dict) -> str:
    """Конвертирует слово используя карту символов"""
    return ''.join(char_map.get(c, c) for c in word)

# Русские слова в английской раскладке (ghbdtn для привет)
RUSSIAN_WORDS_IN_EN_LAYOUT = {
    _convert_word(word, _RU_TO_EN_MAP) for word in RUSSIAN_WORDS
}

# Английские слова в русской раскладке (hell -> рудд)
ENGLISH_WORDS_IN_RU_LAYOUT = {
    _convert_word(word, _EN_TO_RU_MAP) for word in ENGLISH_WORDS
}


def detect_language(word: str) -> str:
    """
    Определяет язык слова по словарю
    
    Args:
        word: слово для определения языка (lowercase)
    
    Returns:
        'ru' - если русское слово
        'en' - если английское слово
        'unknown' - если не удалось определить
    """
    word_lower = word.lower()
    
    # Проверяем в словарях
    if word_lower in RUSSIAN_WORDS:
        return 'ru'
    elif word_lower in ENGLISH_WORDS:
        return 'en'
    
    # Если не нашли в словаре, определяем по символам
    ru_chars = sum(1 for c in word_lower if 'а' <= c <= 'я' or c == 'ё')
    en_chars = sum(1 for c in word_lower if 'a' <= c <= 'z')
    
    if ru_chars > en_chars:
        return 'ru'
    elif en_chars > ru_chars:
        return 'en'
    
    return 'unknown'


def is_likely_wrong_layout(word: str, current_layout: str) -> bool:
    """
    Проверяет, вероятно ли слово набрано в неправильной раскладке
    
    Args:
        word: слово для проверки (например, "ghbdtn" набранное на EN раскладке)
        current_layout: текущая раскладка ('ru' или 'en')
    
    Returns:
        True если слово вероятно набрано в неправильной раскладке
    """
    word_lower = word.lower()
    
    # Если на английской раскладке, проверяем не русское ли это слово
    if current_layout == 'en':
        return word_lower in RUSSIAN_WORDS_IN_EN_LAYOUT
    
    # Если на русской раскладке, проверяем не английское ли это слово
    elif current_layout == 'ru':
        return word_lower in ENGLISH_WORDS_IN_RU_LAYOUT
    
    return False
