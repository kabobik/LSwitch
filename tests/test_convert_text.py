import lswitch


def test_convert_text_roundtrip():
    s = 'j,sxysq'
    conv = lswitch.LSwitch().convert_text(s)
    back = lswitch.LSwitch().convert_text(conv)
    assert conv == 'обычный'
    assert back == s


def test_convert_preserves_case():
    s = 'Ghbdtn'
    # G->? but ensure case handling does not crash and length preserved
    conv = lswitch.LSwitch().convert_text(s)
    assert isinstance(conv, str)
    assert len(conv) == len(s)