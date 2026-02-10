import os
import json
import types
import subprocess

import pytest

import lswitch.xkb as xkb


def test_get_layouts_from_runtime_file(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    data = {'layouts': ['en', 'ru']}
    p = runtime / 'lswitch_layouts.json'
    p.write_text(json.dumps(data), encoding='utf-8')

    monkeypatch.setenv('XDG_RUNTIME_DIR', str(runtime))

    out = xkb.get_layouts_from_xkb(debug=True)
    assert out == ['en', 'ru']


def test_get_layouts_from_setxkbmap(monkeypatch):
    class FakeRes:
        stdout = 'layout: us,ru\n'
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: FakeRes())
    out = xkb.get_layouts_from_xkb(debug=True)
    assert out == ['en', 'ru']


def test_get_current_layout_fallback(monkeypatch):
    monkeypatch.setattr(xkb, 'XKB_AVAILABLE', False)
    monkeypatch.setattr(xkb, 'libX11', None)
    assert xkb.get_current_layout(['en', 'ru']) == 'en'


def test_keycode_to_char_no_lib(monkeypatch):
    monkeypatch.setattr(xkb, 'XKB_AVAILABLE', False)
    monkeypatch.setattr(xkb, 'libX11', None)
    assert xkb.keycode_to_char(30, 'en', ['en', 'ru']) == ''
