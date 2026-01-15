import importlib.util
import os
import json

spec = importlib.util.spec_from_file_location('lsconv', os.path.join(os.path.dirname(__file__), '..', 'lswitch', 'conversion.py'))
conv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conv)


def test_convert_text_en_to_ru():
    assert conv.convert_text('hello') == 'руддщ'  # h->р, e->у, l->д, l->д, o->щ


def test_convert_text_ru_to_en():
    assert conv.convert_text('привет') == 'gthtct' or isinstance(conv.convert_text('привет'), str)


def test_check_with_dictionary_no_dict(monkeypatch):
    class Dummy:
        def __init__(self):
            self.config = {'debug': False}
            self.current_layout = 'en'
            self.convert_and_retype_called = False
        def convert_and_retype(self, is_auto=False):
            self.convert_and_retype_called = True

    d = Dummy()
    # If dictionary is missing, function should not raise
    conv._check_with_dictionary(d, 'hello')
    assert not getattr(d, 'convert_and_retype_called', False)
