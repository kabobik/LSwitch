import json
import os
import pytest

from lswitch import core
from lswitch.core import validate_config


def test_validate_config_good():
    conf = {'double_click_timeout': '0.5', 'debug': True, 'user_dict_min_weight': 3}
    out = validate_config(conf)
    assert isinstance(out['double_click_timeout'], float)
    assert out['double_click_timeout'] == 0.5
    assert out['debug'] is True
    assert out['user_dict_min_weight'] == 3


def test_validate_config_bad_timeout():
    with pytest.raises(ValueError):
        validate_config({'double_click_timeout': 'not-a-number'})


def test_load_config_from_file_and_lswitch_init(tmp_path, monkeypatch):
    # Prepare config file
    cfg = {'double_click_timeout': 1.2, 'debug': False}
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg), encoding='utf-8')

    # Monkeypatch display to avoid connecting to a real X server
    class DummyDisplay:
        def __init__(self):
            pass
    monkeypatch.setattr(core, 'display', type('m', (object,), {'Display': lambda *a, **k: DummyDisplay()}))

    # Monkeypatch evdev.UInput to avoid creating a real uinput device
    class DummyUInput:
        def __init__(self, *a, **k):
            pass
        def close(self):
            pass
        def write(self, *a, **k):
            pass
        def syn(self):
            pass

    monkeypatch.setattr(core, 'evdev', type('m', (object,), {'UInput': DummyUInput}))

    # Ensure user config does not interfere with test
    monkeypatch.setenv('HOME', str(tmp_path))

    # Initialize LSwitch with the temp config and without starting background threads
    ls = core.LSwitch(config_path=str(p), start_threads=False)

    # Assertions
    assert ls.config['double_click_timeout'] == 1.2
    assert ls.config['_config_path'] == str(p)
    assert ls.double_click_timeout == 1.2
    assert ls.layout_thread is None
    assert ls.conversion_manager is None
