import time
from lswitch.conversion import ConversionManager


class DummyUserDict:
    def __init__(self):
        self.added = []
        self.data = {'settings': {'correction_timeout': 2.0}}

    def _canonicalize(self, s, lang):
        # simple canonicalization for tests
        return s.strip().lower()

    def add_correction(self, word, lang, debug=False):
        self.added.append((word, lang))


def test_is_correction_true():
    cm = ConversionManager()
    ud = DummyUserDict()
    auto_marker = {'converted_to': 'обычный', 'word': 'j,sxysq', 'time': time.time()}
    # Simulate: auto converted 'j,sxysq' -> 'обычный', user manually converted back 'обычный' -> 'j,sxysq'
    orig = 'обычный'
    conv = 'j,sxysq'

    assert cm.is_correction(auto_marker, orig, conv, user_dict=ud, timeout=5.0)
    applied = cm.apply_correction(ud, auto_marker, orig, conv, debug=True)
    assert applied
    assert ud.added == [('j,sxysq', 'en')]


def test_is_correction_timeouts():
    cm = ConversionManager()
    ud = DummyUserDict()
    auto_marker = {'converted_to': 'обычный', 'word': 'j,sxysq', 'time': time.time() - 10}
    orig = 'j,sxysq'
    conv = 'обычный'

    assert not cm.is_correction(auto_marker, orig, conv, user_dict=ud, timeout=1.0)
    assert not cm.apply_correction(ud, auto_marker, orig, conv)
    assert ud.added == []


def test_is_correction_mismatch():
    cm = ConversionManager()
    ud = DummyUserDict()
    auto_marker = {'converted_to': 'другое', 'word': 'abc', 'time': time.time()}
    orig = 'j,sxysq'
    conv = 'обычный'

    assert not cm.is_correction(auto_marker, orig, conv, user_dict=ud, timeout=5.0)
    assert not cm.apply_correction(ud, auto_marker, orig, conv)
    assert ud.added == []
