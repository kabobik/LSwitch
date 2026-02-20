import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
sys.path.insert(0, os.getcwd())

from lswitch.device_manager import DeviceManager


class TestDeviceManager:
    """Tests for DeviceManager class."""
    
    def test_device_count_starts_at_zero(self):
        """Test that device_count starts at 0."""
        dm = DeviceManager(debug=False)
        assert dm.device_count == 0
        dm.close()
    
    def test_set_virtual_kb_name(self):
        """Test setting virtual keyboard name for filtering."""
        dm = DeviceManager(debug=False)
        dm.set_virtual_kb_name('LSwitch')
        assert dm._virtual_kb_name == 'LSwitch'
        dm.close()
    
    def test_is_suitable_device_filters_virtual_kb(self):
        """Test that _is_suitable_device filters virtual keyboard."""
        dm = DeviceManager(debug=False)
        dm.set_virtual_kb_name('LSwitch')
        
        mock_device = MagicMock()
        mock_device.name = 'LSwitch Virtual Keyboard'
        mock_device.capabilities.return_value = {1: [30]}  # Has KEY_A
        
        result = dm._is_suitable_device(mock_device)
        assert result is False
        dm.close()
    
    def test_is_suitable_device_accepts_keyboard(self):
        """Test that _is_suitable_device accepts keyboards."""
        dm = DeviceManager(debug=False)
        
        mock_device = MagicMock()
        mock_device.name = 'Real Keyboard'
        mock_device.capabilities.return_value = {1: [30]}  # EV_KEY with KEY_A
        
        result = dm._is_suitable_device(mock_device)
        assert result is True
        dm.close()
    
    def test_is_suitable_device_accepts_mouse(self):
        """Test that _is_suitable_device accepts mice."""
        dm = DeviceManager(debug=False)
        
        mock_device = MagicMock()
        mock_device.name = 'Mouse'
        mock_device.capabilities.return_value = {1: [272]}  # EV_KEY with BTN_LEFT
        
        result = dm._is_suitable_device(mock_device)
        assert result is True
        dm.close()
    
    def test_is_suitable_device_rejects_no_ev_key(self):
        """Test that _is_suitable_device rejects devices without EV_KEY."""
        dm = DeviceManager(debug=False)
        
        mock_device = MagicMock()
        mock_device.name = 'Touchpad'
        mock_device.capabilities.return_value = {2: [0, 1]}  # EV_REL only
        
        result = dm._is_suitable_device(mock_device)
        assert result is False
        dm.close()
    
    def test_remove_device_nonexistent(self):
        """Test removing non-existent device returns False."""
        dm = DeviceManager(debug=False)
        result = dm.remove_device('/dev/input/event999')
        assert result is False
        dm.close()
    
    def test_remove_device_existing(self):
        """Test removing existing device."""
        dm = DeviceManager(debug=False)
        
        mock_device = MagicMock()
        mock_device.name = 'Test Device'
        mock_device.path = '/dev/input/event99'
        
        dm.devices['/dev/input/event99'] = mock_device
        
        result = dm.remove_device('/dev/input/event99')
        
        assert result is True
        assert dm.device_count == 0
        mock_device.close.assert_called_once()
        dm.close()
    
    def test_callbacks_on_remove(self):
        """Test that on_device_removed callback is called."""
        removed = []
        dm = DeviceManager(
            debug=False,
            on_device_removed=lambda d: removed.append(d.name)
        )
        
        mock_device = MagicMock()
        mock_device.name = 'Disconnected Device'
        mock_device.path = '/dev/input/event50'
        
        dm.devices['/dev/input/event50'] = mock_device
        dm.remove_device('/dev/input/event50')
        
        assert 'Disconnected Device' in removed
        dm.close()
    
    def test_handle_read_error_removes_device(self):
        """Test that handle_read_error removes the device."""
        dm = DeviceManager(debug=False)
        
        mock_device = MagicMock()
        mock_device.name = 'Failing Device'
        mock_device.path = '/dev/input/event77'
        
        dm.devices['/dev/input/event77'] = mock_device
        dm.handle_read_error(mock_device, OSError("Device unplugged"))
        
        assert dm.device_count == 0
        dm.close()
    
    def test_context_manager(self):
        """Test context manager protocol."""
        with DeviceManager(debug=False) as dm:
            assert dm is not None
            assert dm.device_count == 0
    
    def test_udev_not_started_without_pyudev(self):
        """Test that udev monitor gracefully handles missing pyudev."""
        with patch.object(
            sys.modules['lswitch.device_manager'], 
            'PYUDEV_AVAILABLE', 
            False
        ):
            dm = DeviceManager(debug=True)
            result = dm.start_udev_monitor()
            assert result is False
            dm.close()
    
    def test_stop_udev_monitor_without_start(self):
        """Test stopping udev monitor when not started."""
        dm = DeviceManager(debug=False)
        dm.stop_udev_monitor()  # Should not raise
        dm.close()
