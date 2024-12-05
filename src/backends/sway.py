import subprocess
import json
from PyQt5.QtCore import QThread, pyqtSignal
from sys import path
path.append("../")
from yawns_notifications import BaseYawn


class FullscreenMonitor(QThread):
    fullscreen_active = pyqtSignal(bool)

    def __init__(self):
        super().__init__()

    def run(self):
        process = subprocess.Popen(
            ['swaymsg', '-t', 'subscribe', '["window"]', '-m'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        while True:
            line = process.stdout.readline()
            event = json.loads(line)
            if event.get("fullscreen_mode") == "1":
                self.fullscreen_active.emit(True)
            else:
                self.fullscreen_active.emit(False)
