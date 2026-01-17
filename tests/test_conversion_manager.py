import pytest
from lswitch.conversion import ConversionManager


class DummyBuffer:
    def __init__(self, chars):
        self.chars_in_buffer = chars


def test_choose_selection_on_backspace_hold():
    cm = ConversionManager(config={})
    buf = DummyBuffer(chars=5)

    mode = cm.choose_mode(buf, lambda: False, backspace_hold=True)
    assert mode == 'selection'


def test_choose_selection_on_empty_buffer():
    cm = ConversionManager(config={})
    buf = DummyBuffer(chars=0)

    mode = cm.choose_mode(buf, lambda: False, backspace_hold=False)
    assert mode == 'selection'


def test_choose_selection_if_has_selection():
    cm = ConversionManager(config={})
    buf = DummyBuffer(chars=5)

    mode = cm.choose_mode(buf, lambda: True, backspace_hold=False)
    assert mode == 'selection'


def test_choose_retype_by_default():
    cm = ConversionManager(config={})
    buf = DummyBuffer(chars=5)

    mode = cm.choose_mode(buf, lambda: False, backspace_hold=False)
    assert mode == 'retype'


def test_config_prefer_retype():
    cm = ConversionManager(config={'prefer_retype_when_possible': True})
    buf = DummyBuffer(chars=5)

    mode = cm.choose_mode(buf, lambda: False, backspace_hold=False)
    assert mode == 'retype'


def test_execute_invokes_callbacks():
    cm = ConversionManager()
    called = {'r': False, 's': False}

    def rcb():
        called['r'] = True

    def scb():
        called['s'] = True

    cm.execute('retype', rcb, scb)
    assert called['r'] and not called['s']

    called['r'] = False
    cm.execute('selection', rcb, scb)
    assert called['s'] and not called['r']
