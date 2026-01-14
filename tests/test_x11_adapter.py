import importlib
import types
import pytest

import adapters.x11 as x11


def test_expand_selection_to_space_basic(monkeypatch):
    seq = ['abc', 'abc', ' abc', ' abc']
    calls = {'i': 0}

    def fake_get_primary(timeout=0.2):
        val = seq[calls['i']] if calls['i'] < len(seq) else seq[-1]
        return val

    def fake_shift():
        calls['i'] += 1

    monkeypatch.setattr(x11, 'get_primary_selection', fake_get_primary)
    monkeypatch.setattr(x11, 'shift_left', fake_shift)

    res = x11.expand_selection_to_space(max_steps=10, stable_timeout=0.1)
    assert ' ' in res


def test_safe_replace_selection_cut_success(monkeypatch):
    # Simulate cut working: cut_selection sets clipboard to selected_text
    state = {'clip': '', 'primary': 'hello'}

    def fake_get_clipboard(timeout=0.3):
        return state['clip']

    def fake_set_clipboard(text):
        state['clip'] = text

    def fake_cut():
        state['clip'] = state['primary']
        state['primary'] = ''

    def fake_paste():
        state['primary'] = state['clip']

    def fake_get_primary(timeout=0.3):
        return state['primary']

    monkeypatch.setattr(x11, 'get_clipboard', fake_get_clipboard)
    monkeypatch.setattr(x11, 'set_clipboard', fake_set_clipboard)
    monkeypatch.setattr(x11, 'cut_selection', fake_cut)
    monkeypatch.setattr(x11, 'paste_clipboard', fake_paste)
    monkeypatch.setattr(x11, 'get_primary_selection', fake_get_primary)

    out = x11.safe_replace_selection('WORLD', selected_text='hello', debug=True)
    assert out == 'WORLD' or out == 'WORLD'  # primary updated


def test_safe_replace_selection_cut_fails_then_delete(monkeypatch):
    state = {'clip': 'old', 'primary': 'abc,def'}

    def fake_get_clipboard(timeout=0.3):
        return state['clip']

    def fake_set_clipboard(text):
        state['clip'] = text

    def fake_cut():
        # Simulate app that ignores ctrl+x (no change)
        pass

    def fake_delete():
        state['primary'] = ''

    def fake_paste():
        state['primary'] = state['clip']

    def fake_get_primary(timeout=0.3):
        return state['primary']

    monkeypatch.setattr(x11, 'get_clipboard', fake_get_clipboard)
    monkeypatch.setattr(x11, 'set_clipboard', fake_set_clipboard)
    monkeypatch.setattr(x11, 'cut_selection', fake_cut)
    monkeypatch.setattr(x11, 'delete_selection', fake_delete)
    monkeypatch.setattr(x11, 'paste_clipboard', fake_paste)
    monkeypatch.setattr(x11, 'get_primary_selection', fake_get_primary)

    out = x11.safe_replace_selection('NEW', selected_text='abc,def', debug=True)
    assert out == 'NEW'
