import sys
import signal
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

app = QApplication(sys.argv)

def sigint_handler(signum, frame):
    print("Caught SIGINT, quitting app...")
    app.quit()

signal.signal(signal.SIGINT, sigint_handler)

timer = QTimer()
timer.timeout.connect(lambda: None)
timer.start(500)

print("Running...")
app.exec_()
print("Clean exit.")
