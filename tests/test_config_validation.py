import json
import tempfile
import os
import pytest
from lswitch.core import validate_config


def test_validate_config_ok():
    cfg = {
        'double_click_timeout': 0.5,
        'debug': True,
        'switch_layout_after_convert': False,
        'layout_switch_key': 'Alt+Shift',
        'auto_switch': True,
        'user_dict_enabled': True,
        'user_dict_min_weight': 3
    }

    normalized = validate_config(cfg)
    assert isinstance(normalized, dict)
    assert normalized['double_click_timeout'] == 0.5
    assert normalized['debug'] is True
    assert normalized['switch_layout_after_convert'] is False
    assert normalized['layout_switch_key'] == 'Alt+Shift'
    assert normalized['auto_switch'] is True
    assert normalized['user_dict_enabled'] is True
    assert normalized['user_dict_min_weight'] == 3


@pytest.mark.parametrize('bad', [None, 'abc', -1, 0])
def test_validate_config_bad_timeout(bad):
    with pytest.raises(ValueError):
        validate_config({'double_click_timeout': bad})


def test_validate_config_bad_types():
    with pytest.raises(ValueError):
        validate_config({'debug': 'yes'})
    with pytest.raises(ValueError):
        validate_config({'switch_layout_after_convert': 'no'})
    with pytest.raises(ValueError):
        validate_config({'layout_switch_key': ''})
    with pytest.raises(ValueError):
        validate_config({'auto_switch': 'maybe'})
    with pytest.raises(ValueError):
        validate_config({'user_dict_enabled': 'maybe'})
    with pytest.raises(ValueError):
        validate_config({'user_dict_min_weight': -5})
