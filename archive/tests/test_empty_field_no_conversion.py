# tests/test_empty_field_no_conversion.py
"""Test that conversion in empty field does not insert old text.

ROOT CAUSE: After ctrl_shift_left() in empty field, PRIMARY clipboard doesn't change,
but convert_selection() still reads text from PRIMARY and inserts it.

FIX: Check if selection owner changed after ctrl_shift_left using XGetSelectionOwner.
If owner unchanged AND text unchanged — skip conversion.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import sys
import os

sys.path.insert(0, os.getcwd())


class MockBuffer:
    """Mock buffer for testing."""
    def __init__(self, chars=0):
        self.chars_in_buffer = chars


def test_ctrl_shift_left_unchanged_owner_and_primary_skips_conversion_input_handler():
    """If ctrl_shift_left doesn't change owner AND text, skip conversion (empty field)."""
    from lswitch.input import InputHandler
    
    # Create mock LSwitch
    ls = MagicMock()
    ls.config = {'debug': True}
    ls.last_known_selection = ""  # Пустой (after click in empty field)
    ls.chars_in_buffer = 0
    ls.backspace_hold_detected = False
    ls.buffer = MockBuffer(chars=0)
    ls.has_selection = MagicMock(return_value=False)
    
    # Setup conversion_manager to select 'selection' mode
    ls.conversion_manager = MagicMock()
    ls.conversion_manager.choose_mode = MagicMock(return_value='selection')
    
    # PRIMARY не меняется после ctrl_shift_left И пустой (пустое поле)
    result_mock = MagicMock()
    result_mock.stdout = ""  # Пустой!
    ls.system = MagicMock()
    ls.system.xclip_get = MagicMock(return_value=result_mock)
    
    handler = InputHandler(ls)
    handler._shift_pressed = False
    
    # Mock adapter и get_selection_owner_id (owner не меняется = 12345)
    with patch('lswitch.input.system'):
        with patch('lswitch.x11_adapter', None, create=True):
            with patch('lswitch.xkb.get_selection_owner_id', return_value=12345):
                handler.on_double_shift()
    
    # convert_selection НЕ должен вызываться (пустое поле, owner не изменился)
    ls.convert_selection.assert_not_called()
    # convert_and_retype тоже НЕ должен вызываться
    ls.convert_and_retype.assert_not_called()
    # last_shift_press должен сброситься
    assert ls.last_shift_press == 0


def test_ctrl_shift_left_changed_owner_does_conversion():
    """If ctrl_shift_left changes selection owner, proceed with conversion."""
    from lswitch.input import InputHandler
    
    # Create mock LSwitch
    ls = MagicMock()
    ls.config = {'debug': True}
    ls.last_known_selection = "old text"
    ls.chars_in_buffer = 0
    ls.backspace_hold_detected = False
    ls.buffer = MockBuffer(chars=0)
    ls.has_selection = MagicMock(return_value=False)
    
    # Setup conversion_manager to select 'selection' mode
    ls.conversion_manager = MagicMock()
    ls.conversion_manager.choose_mode = MagicMock(return_value='selection')
    
    # PRIMARY тот же, но owner изменился (новое выделение!)
    result_mock = MagicMock()
    result_mock.stdout = "old text"  # Текст тот же
    ls.system = MagicMock()
    ls.system.xclip_get = MagicMock(return_value=result_mock)
    
    handler = InputHandler(ls)
    handler._shift_pressed = False
    
    # Owner меняется: before=12345, after=67890
    owner_call_count = [0]
    def mock_get_owner():
        owner_call_count[0] += 1
        return 12345 if owner_call_count[0] == 1 else 67890
    
    with patch('lswitch.input.system'):
        with patch('lswitch.x11_adapter', None, create=True):
            with patch('lswitch.xkb.get_selection_owner_id', side_effect=mock_get_owner):
                handler.on_double_shift()
    
    # convert_selection ДОЛЖЕН вызваться (owner изменился)
    ls.convert_selection.assert_called()


def test_ctrl_shift_left_changed_primary_does_conversion():
    """If ctrl_shift_left changes PRIMARY text, proceed with conversion."""
    from lswitch.input import InputHandler
    
    # Create mock LSwitch
    ls = MagicMock()
    ls.config = {'debug': True}
    ls.last_known_selection = "old text"
    ls.chars_in_buffer = 0
    ls.backspace_hold_detected = False
    ls.buffer = MockBuffer(chars=0)
    ls.has_selection = MagicMock(return_value=False)
    
    # Setup conversion_manager to select 'selection' mode
    ls.conversion_manager = MagicMock()
    ls.conversion_manager.choose_mode = MagicMock(return_value='selection')
    
    # PRIMARY меняется после ctrl_shift_left
    result_mock = MagicMock()
    result_mock.stdout = "new selected word"  # Другой текст!
    ls.system = MagicMock()
    ls.system.xclip_get = MagicMock(return_value=result_mock)
    
    handler = InputHandler(ls)
    handler._shift_pressed = False
    
    # Mock adapter и get_selection_owner_id (owner тот же, но текст изменился)
    with patch('lswitch.input.system'):
        with patch('lswitch.x11_adapter', None, create=True):
            with patch('lswitch.xkb.get_selection_owner_id', return_value=12345):
                handler.on_double_shift()
    
    # convert_selection ДОЛЖЕН вызваться (текст изменился)
    ls.convert_selection.assert_called()


def test_unchanged_primary_with_new_owner_does_conversion():
    """If owner changed (new selection of same text), proceed with conversion."""
    from lswitch.input import InputHandler
    
    # Сценарий: пользователь выделил "hello", кликнул в другое место,
    # затем снова выделил то же слово "hello" и нажал double-shift
    # Owner ИЗМЕНИТСЯ потому что это НОВОЕ выделение!
    
    ls = MagicMock()
    ls.config = {'debug': True}
    ls.last_known_selection = "hello"  # После клика snapshot = текущий PRIMARY
    ls.chars_in_buffer = 0
    ls.backspace_hold_detected = False
    ls.buffer = MockBuffer(chars=0)
    ls.has_selection = MagicMock(return_value=False)
    
    ls.conversion_manager = MagicMock()
    ls.conversion_manager.choose_mode = MagicMock(return_value='selection')
    
    # PRIMARY не изменился после ctrl_shift_left
    result_mock = MagicMock()
    result_mock.stdout = "hello"  # Тот же текст
    ls.system = MagicMock()
    ls.system.xclip_get = MagicMock(return_value=result_mock)
    
    handler = InputHandler(ls)
    handler._shift_pressed = False
    
    # Owner меняется: before=12345, after=67890 (новое выделение!)
    owner_call_count = [0]
    def mock_get_owner():
        owner_call_count[0] += 1
        return 12345 if owner_call_count[0] == 1 else 67890
    
    with patch('lswitch.input.system'):
        with patch('lswitch.x11_adapter', None, create=True):
            with patch('lswitch.xkb.get_selection_owner_id', side_effect=mock_get_owner):
                handler.on_double_shift()
    
    # convert_selection ДОЛЖЕН вызваться (owner изменился = новое выделение!)
    ls.convert_selection.assert_called()

def test_ctrl_shift_left_with_existing_selection_skips_owner_check():
    """If selection already exists, don't check owner change."""
    from lswitch.input import InputHandler
    
    # Create mock LSwitch
    ls = MagicMock()
    ls.config = {'debug': True}
    ls.last_known_selection = "same text"
    ls.chars_in_buffer = 0
    ls.backspace_hold_detected = False
    ls.buffer = MockBuffer(chars=0)
    ls.has_selection = MagicMock(return_value=True)  # Уже есть выделение!
    
    # Setup conversion_manager to select 'selection' mode
    ls.conversion_manager = MagicMock()
    ls.conversion_manager.choose_mode = MagicMock(return_value='selection')
    
    ls.system = MagicMock()
    
    handler = InputHandler(ls)
    handler._shift_pressed = False
    
    # Mock adapter — get_selection_owner_id НЕ должен вызываться
    with patch('lswitch.input.system'):
        with patch('lswitch.x11_adapter', None, create=True):
            with patch('lswitch.xkb.get_selection_owner_id') as mock_owner:
                handler.on_double_shift()
                # get_selection_owner_id НЕ вызывается когда выделение уже есть
                mock_owner.assert_not_called()
    
    # convert_selection ДОЛЖЕН вызваться (есть выделение)
    ls.convert_selection.assert_called()
    # xclip_get НЕ должен вызываться (проверка PRIMARY пропускается)
    ls.system.xclip_get.assert_not_called()


def test_empty_field_scenario_full():
    """Full scenario: click on empty field, then double-shift should not insert old text."""
    from lswitch.input import InputHandler
    
    # Симулируем сценарий:
    # 1. Клик в пустое поле -> update_selection_snapshot() сохраняет текущий PRIMARY
    # 2. Double-shift
    # 3. ctrl_shift_left не меняет PRIMARY (поле пустое, NO-OP)
    # 4. Owner не меняется, PRIMARY пустой -> пропускаем конвертацию
    
    ls = MagicMock()
    ls.config = {'debug': True}
    ls.last_known_selection = ""  # После клика в пустое поле snapshot пустой
    ls.chars_in_buffer = 0
    ls.backspace_hold_detected = False
    ls.buffer = MockBuffer(chars=0)
    ls.has_selection = MagicMock(return_value=False)
    
    ls.conversion_manager = MagicMock()
    ls.conversion_manager.choose_mode = MagicMock(return_value='selection')
    
    # После ctrl_shift_left PRIMARY остаётся пустым
    result_mock = MagicMock()
    result_mock.stdout = ""  # Пустой!
    ls.system = MagicMock()
    ls.system.xclip_get = MagicMock(return_value=result_mock)
    
    handler = InputHandler(ls)
    handler._shift_pressed = False
    
    # Owner не меняется (пустое поле)
    with patch('lswitch.input.system'):
        with patch('lswitch.x11_adapter', None, create=True):
            with patch('lswitch.xkb.get_selection_owner_id', return_value=12345):
                handler.on_double_shift()
    
    # Главное: convert_selection НЕ вызывается (пустое поле, owner не изменился)
    ls.convert_selection.assert_not_called()
    ls.convert_and_retype.assert_not_called()
