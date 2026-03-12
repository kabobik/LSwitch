import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

app = QApplication(sys.argv)
timer = QTimer()
timer.timeout.connect(lambda: None)
timer.start(500)

try:
    print("Running GUI loop, try pressing Ctrl+C...")
    app.exec_()
except KeyboardInterrupt:
    print("Caught KeyboardInterrupt!")
finally:
    print("Cleanup done.")
