import pytest
import lswitch


@pytest.mark.parametrize("s", [
    "j,sxysq", "ghbdtn", "ytdthysq", "hello,world", "test.case", "Ghbdtn", "a", ","
])
def test_convert_text_roundtrip_various(s):
    ls = lswitch.LSwitch(config_path='config.json')
    conv = ls.convert_text(s)
    back = ls.convert_text(conv)
    assert back == s


def test_convert_text_specific():
    s = 'j,sxysq'
    conv = lswitch.LSwitch().convert_text(s)
    assert conv == 'обычный'


def test_convert_preserves_case():
    s = 'Ghbdtn'
    # ensure case handling does not crash and length preserved
    conv = lswitch.LSwitch().convert_text(s)
    assert isinstance(conv, str)
    assert len(conv) == len(s)