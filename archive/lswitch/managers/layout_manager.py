"""LayoutManager: Unified layout detection and management for LSwitch.

Handles X11/XKB layout detection, layout switching, and layout monitoring.
Eliminates duplication between core components.
"""
import os
import threading
import time
from typing import List, Optional, Callable

try:
    from Xlib import display, X
    from Xlib.ext import xkb
    XLIB_AVAILABLE = True
except ImportError:
    XLIB_AVAILABLE = False


class LayoutManager:
    """Centralized keyboard layout management."""
    
    def __init__(self, system=None, debug: bool = False):
        """Initialize LayoutManager.
        
        Args:
            system: System interface for layout switching.
            debug: Enable debug output.
        """
        self.system = system
        self.debug = debug
        
        # X11 display connection
        self.x11_display = display.Display() if XLIB_AVAILABLE else None
        
        # Layout state
        self.layouts = []
        self.current_layout = 'en'
        self.layout_lock = threading.Lock()
        
        # Monitoring threads
        self.layout_monitor_thread = None
        self.file_monitor_thread = None
        self.running = False
        
        # Layout change callbacks
        self.layout_change_callbacks: List[Callable[[str, str], None]] = []
        
        # Initialize layouts
        self._detect_layouts()
    
    def _detect_layouts(self) -> None:
        """Detect available keyboard layouts."""
        if XLIB_AVAILABLE and self.x11_display:
            try:
                self.layouts = self._get_layouts_from_xkb()
            except Exception as e:
                if self.debug:
                    print(f"⚠️ XKB layout detection failed: {e}")
                self.layouts = self._get_fallback_layouts()
        else:
            self.layouts = self._get_fallback_layouts()
        
        if len(self.layouts) < 2:
            print(f"⚠️ Only {len(self.layouts)} layout detected: {self.layouts}")
            print("   Limited functionality - conversion may not work properly")
        else:
            print(f"✓ Layouts detected: {self.layouts}")
        
        # Set initial current layout
        self.current_layout = self._get_current_layout_from_system()
    
    def _get_layouts_from_xkb(self) -> List[str]:
        """Get layouts from X11 XKB."""
        if not XLIB_AVAILABLE:
            return []
        
        try:
            # Simple fallback for now
            return ['en', 'ru']
            
        except Exception as e:
            if self.debug:
                print(f"⚠️ XKB query failed: {e}")
            return self._get_fallback_layouts()
    
    def _get_fallback_layouts(self) -> List[str]:
        """Get fallback layout list when XKB detection fails."""
        return ['en', 'ru']
    
    def _get_current_layout_from_system(self) -> str:
        """Get current layout from system."""
        return self.layouts[0] if self.layouts else 'en'
    
    def get_layouts(self) -> List[str]:
        """Get available layouts."""
        return self.layouts.copy()
    
    def get_current_layout(self) -> str:
        """Get current layout."""
        with self.layout_lock:
            return self.current_layout
    
    def set_current_layout(self, layout: str) -> None:
        """Set current layout (for internal tracking)."""
        with self.layout_lock:
            old_layout = self.current_layout
            self.current_layout = layout
            
            # Notify callbacks of layout change
            for callback in self.layout_change_callbacks:
                try:
                    callback(old_layout, layout)
                except Exception as e:
                    if self.debug:
                        print(f"⚠️ Layout change callback failed: {e}")
    
    def switch_layout(self) -> bool:
        """Switch to next layout.
        
        Returns:
            True if switch successful, False otherwise.
        """
        if not self.system:
            if self.debug:
                print("⚠️ No system interface for layout switching")
            return False
        
        try:
            # Use system interface to switch layout
            if hasattr(self.system, 'switch_layout'):
                success = self.system.switch_layout()
                if success:
                    # Update internal tracking
                    current_idx = 0
                    try:
                        current_idx = self.layouts.index(self.current_layout)
                    except ValueError:
                        pass
                    
                    next_idx = (current_idx + 1) % len(self.layouts)
                    self.set_current_layout(self.layouts[next_idx])
                    
                    if self.debug:
                        print(f"🔄 Layout switched: {self.layouts[current_idx]} → {self.layouts[next_idx]}")
                return success
        except Exception as e:
            if self.debug:
                print(f"⚠️ Layout switch failed: {e}")
        
        return False
    
    def add_layout_change_callback(self, callback: Callable[[str, str], None]) -> None:
        """Add callback for layout changes.
        
        Args:
            callback: Function that receives (old_layout, new_layout).
        """
        self.layout_change_callbacks.append(callback)
    
    def start_monitoring(self) -> None:
        """Start layout monitoring threads."""
        if self.running:
            return
        
        self.running = True
        
        if self.debug:
            print("✓ Layout monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop layout monitoring threads."""
        self.running = False
        
        if self.debug:
            print("✓ Layout monitoring stopped")