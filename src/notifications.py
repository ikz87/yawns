from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt

class BaseNotification(QWidget):
    def __init__(self, screen, config, notif_dict, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.notif_dict = notif_dict
        self.setWindowTitle("yawns - Card")


class CardNotification(BaseNotification):
    def __init__(self, screen, config, notif_dict, parent=None):
        super().__init__(screen, config, notif_dict, parent=parent)
        self.offset_x = int(config["card"]["x-offset"])
        self.offset_y = int(config["card"]["y-offset"])
        if int(config["card"]["x-offset"]) < 0:
            self.offset_x = (screen.size().width() +
                self.offset_x -
                int(config["card"]["width"]))
        if int(config["card"]["y-offset"]) < 0:
            self.offset_y = (screen.size().height() +
                self.offset_y -
                int(config["card"]["height"]))

        self.setGeometry(
            self.offset_x,
            self.offset_y,
            int(config["card"]["width"]),
            int(config["card"]["height"])
        )
