import importlib
import types
import pytest

import lswitch.adapters.x11 as x11


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
    # Simulate xclip_set + paste inserting the converted text
    state = {'clip': '', 'primary': 'hello'}

    def fake_get_clipboard(timeout=0.3):
        return state['clip']

    def fake_set_clipboard(text, timeout=0.5):
        state['clip'] = text

    def fake_paste():
        # Paste inserts clipboard content to primary
        state['primary'] = state['clip']

    def fake_get_primary(timeout=0.3):
        return state['primary']

    # Mock the system's xclip_set to set PRIMARY selection
    class FakeSystem:
        def xclip_set(self, text, selection='clipboard', timeout=0.5):
            if selection == 'primary':
                state['primary'] = text
            else:
                state['clip'] = text

    def fake_get_system():
        return FakeSystem()

    monkeypatch.setattr(x11, 'get_clipboard', fake_get_clipboard)
    monkeypatch.setattr(x11, 'set_clipboard', fake_set_clipboard)
    monkeypatch.setattr(x11, 'paste_clipboard', fake_paste)
    monkeypatch.setattr(x11, 'get_primary_selection', fake_get_primary)
    monkeypatch.setattr(x11, 'get_system', fake_get_system)

    out = x11.safe_replace_selection('WORLD', selected_text='hello', debug=True)
    assert out == 'WORLD'  # primary updated with pasted text


def test_safe_replace_selection_cut_fails_then_delete(monkeypatch):
    state = {'clip': 'old', 'primary': 'abc,def'}

    def fake_get_clipboard(timeout=0.3):
        return state['clip']

    def fake_set_clipboard(text, timeout=0.5):
        state['clip'] = text

    def fake_paste():
        # Paste inserts clipboard content
        state['primary'] = state['clip']

    def fake_get_primary(timeout=0.3):
        return state['primary']

    # Mock the system's xclip_set to set PRIMARY selection
    class FakeSystem:
        def xclip_set(self, text, selection='clipboard', timeout=0.5):
            if selection == 'primary':
                state['primary'] = text
            else:
                state['clip'] = text

    def fake_get_system():
        return FakeSystem()

    monkeypatch.setattr(x11, 'get_clipboard', fake_get_clipboard)
    monkeypatch.setattr(x11, 'set_clipboard', fake_set_clipboard)
    monkeypatch.setattr(x11, 'paste_clipboard', fake_paste)
    monkeypatch.setattr(x11, 'get_primary_selection', fake_get_primary)
    monkeypatch.setattr(x11, 'get_system', fake_get_system)

    out = x11.safe_replace_selection('NEW', selected_text='abc,def', debug=True)
    assert out == 'NEW'
