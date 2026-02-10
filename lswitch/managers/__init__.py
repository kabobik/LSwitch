"""LSwitch managers package - unified management classes for core functionality."""

from lswitch.config import ConfigManager
from .layout_manager import LayoutManager

__all__ = ['ConfigManager', 'LayoutManager']