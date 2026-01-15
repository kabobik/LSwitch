import os
import lswitch


def test_shim_exports_core_symbols():
    # The shim should still provide the primary symbols expected by callers/tests
    assert hasattr(lswitch, 'LSwitch')
    # Attributes that previously lived at module level in core must be reachable
    # via the shim for backwards compatibility/mocking
    assert hasattr(lswitch, 'x11_adapter')
    assert hasattr(lswitch, 'XLIB_AVAILABLE')


def test_shim_sets_path():
    root = os.path.dirname(lswitch.__file__)
    assert os.path.join(root, 'lswitch') in lswitch.__path__
