from lswitch.processors.text_processor import TextProcessor
from lswitch.conversion_maps import EN_TO_RU, RU_TO_EN


def _make_processor():
    return TextProcessor(system=None, config={'debug': False})


def test_convert_text_en_to_ru():
    tp = _make_processor()
    assert tp.convert_text('hello') == 'руддщ'


def test_convert_text_ru_to_en():
    tp = _make_processor()
    result = tp.convert_text('привет')
    assert isinstance(result, str) and len(result) > 0


def test_check_with_dictionary_no_dict(monkeypatch):
    """Conversion works even without dictionary."""
    tp = _make_processor()
    # No user_dict set — should still convert without error
    result = tp.convert_text('hello')
    assert result == 'руддщ'
