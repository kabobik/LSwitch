"""LSwitch package — public API"""
from .cli import main
from .core import LSwitch, force_release_virtual_keyboards, register_instance, x11_adapter
__all__ = ["main", "LSwitch", "force_release_virtual_keyboards", "register_instance", "x11_adapter"]
