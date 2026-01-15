import subprocess
import sys
import types

# Provide fake PyQt5 modules when running tests in headless environments
qt_mod = types.ModuleType('PyQt5.QtWidgets')
for name in ('QApplication','QSystemTrayIcon','QAction','QMenu','QWidget','QLabel','QMessageBox'):
    setattr(qt_mod, name, type(name, (), {}))
sys.modules['PyQt5'] = types.ModuleType('PyQt5')
sys.modules['PyQt5.QtWidgets'] = qt_mod
# Provide a minimal QtGui module used by the panel
qt_gui = types.ModuleType('PyQt5.QtGui')
for name in ('QIcon','QPixmap','QPainter','QColor','QPalette','QCursor','QFont'):
    setattr(qt_gui, name, type(name, (), {}))
sys.modules['PyQt5.QtGui'] = qt_gui
# Provide a minimal QtCore module
qt_core = types.ModuleType('PyQt5.QtCore')
for name in ('Qt','QTimer','QEvent','QPoint','QSize'):
    setattr(qt_core, name, type(name, (), {}))
sys.modules['PyQt5.QtCore'] = qt_core

import lswitch_control


def test_reload_service_config_uses_systemctl(monkeypatch):
    calls = []

    def fake_run(args, timeout=None, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, 'run', fake_run)

    panel = lswitch_control.LSwitchControlPanel.__new__(lswitch_control.LSwitchControlPanel)
    # call the method directly
    panel.reload_service_config()

    # First attempt should be systemctl --user kill --signal=HUP lswitch
    assert any('systemctl' in a[0] and '--user' in a and 'kill' in a for a in calls)
