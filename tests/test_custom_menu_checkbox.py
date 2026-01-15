import sys
import os
sys.path.insert(0, os.getcwd())
from adapters.cinnamon import CustomMenuItem
from PyQt5.QtWidgets import QApplication


def test_checkbox_click_emits(monkeypatch):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])

    item = CustomMenuItem('Test', checkable=True)

    called = {'cnt': 0}
    def on_clicked():
        called['cnt'] += 1
    item.clicked.connect(on_clicked)

    # Simulate clicking checkbox via its clicked signal
    item.checkbox.click()
    assert called['cnt'] == 1

    app.quit()
