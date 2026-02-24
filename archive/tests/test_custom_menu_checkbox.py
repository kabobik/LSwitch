import sys
import os
sys.path.insert(0, os.getcwd())
from lswitch.adapters.cinnamon import CustomMenuItem
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtTest import QTest


def test_checkbox_click_emits(monkeypatch):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication([])

    item = CustomMenuItem('Test', checkable=True)

    called = {'cnt': 0}
    def on_clicked():
        called['cnt'] += 1
    item.clicked.connect(on_clicked)

    # Simulate clicking on the item (not the checkbox directly)
    # Checkbox has WA_TransparentForMouseEvents, clicks go through to item
    item.show()
    QTest.mouseClick(item, Qt.LeftButton, pos=QPoint(50, 14))
    assert called['cnt'] == 1

    app.quit()
