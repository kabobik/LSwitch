"""Conversion utilities (text conversion and auto-convert checks).

This module provides pure functions that encapsulate the logic for converting
text between layouts and for deciding / performing auto-conversions. They are
written to be easily testable and to be callable from `LSwitch`.
"""
from __future__ import annotations

import time

# Maps used for conversion (EN -> RU and RU -> EN)
EN_TO_RU = {
    'q': 'й', 'w': 'ц', 'e': 'у', 'r': 'к', 't': 'е', 'y': 'н', 'u': 'г', 'i': 'ш', 'o': 'щ', 'p': 'з',
    '[': 'х', ']': 'ъ', 'a': 'ф', 's': 'ы', 'd': 'в', 'f': 'а', 'g': 'п', 'h': 'р', 'j': 'о', 'k': 'л',
    'l': 'д', ';': 'ж', "'": 'э', 'z': 'я', 'x': 'ч', 'c': 'с', 'v': 'м', 'b': 'и', 'n': 'т', 'm': 'ь',
    ',': 'б', '.': 'ю', '/': '.', '`': 'ё',
    '{': 'х', '}': 'ъ', ':': 'ж', '"': 'э', '<': 'б', '>': 'ю', '?': ',', '~': 'ё',
    '@': '"', '#': '№', '$': ';', '^': ':', '&': '?'
}
RU_TO_EN = {v: k for k, v in EN_TO_RU.items()}
PREFERRED_REVERSE = {
    'б': ',',
    'ю': '.',
    'ё': '`',
    'э': "'",
}
for ru, en in PREFERRED_REVERSE.items():
    RU_TO_EN[ru] = en


def convert_text(text: str) -> str:
    """Convert text between EN and RU preserving case.

    This mirrors the behavior originally implemented as `LSwitch.convert_text`.
    """
    if not text:
        return text

    ru_chars = sum(1 for c in text.lower() if c in RU_TO_EN)
    en_chars = sum(1 for c in text.lower() if c in EN_TO_RU)

    result = []
    if ru_chars > en_chars:
        # RU -> EN
        for c in text:
            is_upper = c.isupper()
            converted = RU_TO_EN.get(c.lower(), c)
            result.append(converted.upper() if is_upper else converted)
    else:
        # EN -> RU
        for c in text:
            is_upper = c.isupper()
            converted = EN_TO_RU.get(c.lower(), c)
            result.append(converted.upper() if is_upper else converted)

    return ''.join(result)


def _check_with_dictionary(ls, text: str):
    """Legacy fallback using dictionary.py; tries to convert and will call
    `ls.convert_and_retype()` if conversion applies.
    """
    try:
        from dictionary import check_word, convert_text as dict_convert

        is_correct, _ = check_word(text, ls.current_layout)
        if not is_correct:
            converted = dict_convert(text, ls.current_layout)
            is_conv_correct, _ = check_word(converted, 'en' if ls.current_layout == 'ru' else 'ru')
            if is_conv_correct:
                if ls.config.get('debug'):
                    print(f"🤖 Auto-convert (dictionary): '{text}' → '{converted}'")
                ls.convert_and_retype()
    except Exception as e:
        if ls.config.get('debug'):
            print(f"⚠️ Error in _check_with_dictionary: {e}")


def check_and_auto_convert(ls):
    """Full auto-conversion flow. Accepts `LSwitch` instance and executes
    conversion as required by its configuration.

    This function mirrors the original `LSwitch.check_and_auto_convert` but
    is placed here to enable testing and easier refactoring.
    """
    if not ls.config.get('auto_switch') or not getattr(ls, 'DICT_AVAILABLE', False):
        if ls.config.get('debug'):
            if not ls.config.get('auto_switch'):
                print("⏭️ Auto-switch disabled in config")
            if not getattr(ls, 'DICT_AVAILABLE', False):
                print("⏭️ Dictionary not available")
        return

    if ls.had_backspace:
        if ls.config.get('debug'):
            print("⏭️ Skip auto-convert: user used backspace")
        return

    if ls.current_layout not in ['ru', 'en']:
        if ls.config.get('debug'):
            print(f"⏭️ Skip auto-convert: unsupported layout {ls.current_layout}")
        return

    if ls.chars_in_buffer == 0:
        return

    text = ''.join(ls.buffer.text_buffer).strip()
    if not text:
        if ls.config.get('debug'):
            print("⏭️ Skip auto-convert: empty buffer")
        return

    try:
        if ls.user_dict and hasattr(ls.user_dict, 'should_auto_convert'):
            has_cyrillic = any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in text)
            from_lang = 'ru' if has_cyrillic else 'en'
            to_lang = 'en' if from_lang == 'ru' else 'ru'

            threshold = ls.user_dict.data.get('settings', {}).get('auto_convert_threshold', 5)
            will = ls.user_dict.should_auto_convert(text, from_lang, to_lang, threshold=threshold)
            if ls.config.get('debug'):
                weight = ls.user_dict.get_conversion_weight(text, from_lang, to_lang)
                print(f"🔎 Auto-convert decision: word='{text}', from={from_lang}, to={to_lang}, weight={weight}, threshold={threshold}, will_convert={will}")

            if will:
                if ls.config.get('debug'):
                    print(f"🎯 Auto-convert (user_dict): '{text}' ({from_lang}→{to_lang}), weight: {weight}")
                converted_text = convert_text(text)
                ls.last_auto_convert = {
                    "word": text,
                    "converted_to": converted_text,
                    "time": time.time(),
                    "lang": from_lang
                }
                ls._recent_auto_marker = dict(ls.last_auto_convert)
                ls.convert_and_retype(is_auto=True)
            else:
                # fallback to dictionary and ngrams
                try:
                    if ls.config.get('debug'):
                        print("  🔁 Trying dictionary fallback (_check_with_dictionary)")
                    _check_with_dictionary(ls, text)
                except Exception as e:
                    if ls.config.get('debug'):
                        print(f"⚠️ dictionary fallback error: {e}")

                try:
                    import ngrams
                    should, best_text, reason = ngrams.should_convert(text, threshold=5, user_dict=ls.user_dict)
                    if ls.config.get('debug'):
                        print(f"🔁 N-gram fallback: should={should}, best='{best_text}', reason={reason}")
                    if should:
                        if ls.config.get('debug'):
                            print(f"🎯 Auto-convert (n-grams): '{text}' → '{best_text}' ({reason})")
                        ls.last_auto_convert = {
                            "word": text,
                            "converted_to": best_text,
                            "time": time.time(),
                            "lang": from_lang
                        }
                        ls._recent_auto_marker = dict(ls.last_auto_convert)
                        ls._override_converted_text = best_text
                        ls.convert_and_retype(is_auto=True)
                        try:
                            del ls._override_converted_text
                        except Exception:
                            pass
                except ImportError:
                    if ls.config.get('debug'):
                        print("⚠️ ngrams.py not available, skipping ngram fallback")
                except Exception as e:
                    if ls.config.get('debug'):
                        print(f"⚠️ ngram fallback error: {e}")

            if ls.config.get('debug'):
                print("  ⏭️ Auto-convert check finished (user_dict path)")
    except ImportError:
        if ls.config.get('debug'):
            print("⚠️ ngrams.py not available, using fallback")
        _check_with_dictionary(ls, text)
    except Exception as e:
        if ls.config.get('debug'):
            import traceback
            print(f"⚠️ Error during auto-convert: {e}")
            traceback.print_exc()
