from lswitch.core.modes import SelectionMode
from lswitch.core.states import StateContext
from lswitch.platform.selection_adapter import SelectionInfo
from unittest.mock import MagicMock

def test_selection_mode_expands_when_backspace_hold_active():
    sel = MagicMock()
    sel.expand_selection_to_word.return_value = SelectionInfo(text="ghbdtn", owner_id=1, timestamp=0.0)
    xkb = MagicMock()
    sys = MagicMock()
    mode = SelectionMode(sel, xkb, sys)
    ctx = StateContext()
    ctx.backspace_hold_active = True
    
    assert mode.execute(ctx) is True
    sel.expand_selection_to_word.assert_called_once()
    sel.get_selection.assert_not_called()
    sel.replace_selection.assert_called_once_with("привет")
