"""EN↔RU keyboard layout conversion maps.

Ported from archive/lswitch/conversion_maps.py — verified, complete.
"""

from __future__ import annotations

EN_TO_RU: dict[str, str] = {
    "q": "й", "w": "ц", "e": "у", "r": "к", "t": "е", "y": "н", "u": "г",
    "i": "ш", "o": "щ", "p": "з", "[": "х", "]": "ъ",
    "a": "ф", "s": "ы", "d": "в", "f": "а", "g": "п", "h": "р",
    "j": "о", "k": "л", "l": "д", ";": "ж", "'": "э",
    "z": "я", "x": "ч", "c": "с", "v": "м", "b": "и", "n": "т",
    "m": "ь", ",": "б", ".": "ю", "/": ".", "`": "ё",
    # Uppercase
    "Q": "Й", "W": "Ц", "E": "У", "R": "К", "T": "Е", "Y": "Н", "U": "Г",
    "I": "Ш", "O": "Щ", "P": "З", "{": "Х", "}": "Ъ",
    "A": "Ф", "S": "Ы", "D": "В", "F": "А", "G": "П", "H": "Р",
    "J": "О", "K": "Л", "L": "Д", ":": "Ж", '"': "Э",
    "Z": "Я", "X": "Ч", "C": "С", "V": "М", "B": "И", "N": "Т",
    "M": "Ь", "<": "Б", ">": "Ю", "?": ",", "~": "Ё",
    # Digits and symbols stay unchanged
    "@": '"', "#": "№", "$": ";", "^": ":", "&": "?",
}

RU_TO_EN: dict[str, str] = {v: k for k, v in EN_TO_RU.items()}
