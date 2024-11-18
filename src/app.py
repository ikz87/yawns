import sys
import configparser
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from notifications import BaseNotification, CardNotification


class YawnsApp(QApplication):
    def __init__(self, appname):
        super().__init__(appname)
        self.notifications = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.create_new_window)
        self.timer.start(1000)  # Trigger every 5 seconds

    def create_new_window(self):
        child_window = CardNotification(SCREEN, CONFIG, {})
        child_window.show()
        self.notifications.append(child_window)

if __name__ == '__main__':
    global SCREEN
    global CONFIGS
    CONFIG = configparser.ConfigParser()
    CONFIG.read('./config.ini')
    app = YawnsApp(["yawns"])
    SCREEN = app.primaryScreen()
    sys.exit(app.exec_())

