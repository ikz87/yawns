from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget, QGridLayout, QLabel, QFrame
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
import time

def empty_layout(layout):
    # Empties a layout recursively
    while layout.count():
        to_delete = layout.itemAt(0)
        if to_delete is not None:
            child_layout = to_delete.layout()
            if child_layout is not None:
                empty_layout(child_layout)
            child_widget = to_delete.widget()
            if child_widget is not None:
                child_widget.deleteLater()
            layout.removeItem(to_delete)

class BaseNotification(QFrame):
    def __init__(self, config, notif_dict, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.X11BypassWindowManagerHint)
        #self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.notif_dict = notif_dict
        timeout = int(config["general"]["timeout"])
        if "expire_timeout" in notif_dict and int(notif_dict["expire_timeout"]) > 0:
            timeout = int(notif_dict["expire_timeout"])
        self.timer = QTimer(self)
        self.timer.setInterval(timeout)
        self.timer.timeout.connect(self.close)
        self.timer.start()


class CardNotification(BaseNotification):
    def __init__(self, app, config, notif_dict, parent=None):
        super().__init__(config, notif_dict, parent=parent)
        self.app = app
        self.notif_dict = notif_dict
        self.config = config
        self.setObjectName("CardNotification")
        self.setFixedWidth(int(config["card"]["width"]))
        self.index = len(app.card_notifications)
        app.card_notifications.append(self)

        # Set up window
        self.setWindowTitle("yawns - Card")

        # Set up content
        self.main_layout = QVBoxLayout(self)
        self.upper_layout = QHBoxLayout()
        self.labels_layout = QVBoxLayout()
        self.main_layout.addStretch()
        self.main_layout.addLayout(self.upper_layout)

        if "image_path" in self.notif_dict:
            path = self.notif_dict["image_path"].replace("file://", "")
            pixmap = QPixmap(path)
            self.icon_label = QLabel()
            self.icon_label.setObjectName("CardIcon")
            if not pixmap.isNull():
                size = int(self.config["card"]["icon-size"])
                pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(pixmap)
                self.upper_layout.addWidget(self.icon_label)
        elif "app_icon" in self.notif_dict:
            path = self.notif_dict["app_icon"].replace("file://", "")
            pixmap = QPixmap(path)
            self.icon_label = QLabel()
            self.icon_label.setObjectName("CardIcon")
            if not pixmap.isNull():
                size = int(self.config["card"]["icon-size"])
                pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(pixmap)
                self.upper_layout.addWidget(self.icon_label)
        self.upper_layout.addLayout(self.labels_layout)
        if "summary" in self.notif_dict:
            self.summary_label = QLabel()
            self.summary_label.setText(self.notif_dict["summary"])
            self.summary_label.setWordWrap(True)
            self.summary_label.setObjectName("CardSummary")
            self.labels_layout.addWidget(self.summary_label)
        if "body" in self.notif_dict:
            self.body_label = QLabel()
            self.body_label.setText(self.notif_dict["body"])
            self.body_label.setWordWrap(True)
            self.body_label.setObjectName("CardBody")
            self.labels_layout.addWidget(self.body_label)

        self.upper_layout.addStretch()
        self.main_layout.addStretch()

        # Set up position
        self.resize(self.sizeHint())

        self.update_position()

    def update_content(self):
        # Restart the timer
        self.timer.stop()
        self.timer.start()

        if "image_path" in self.notif_dict:
            path = self.notif_dict["image_path"].replace("file://", "")
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                size = int(self.config["card"]["icon-size"])
                pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(pixmap)
            else:
                self.icon_label.clear()

        elif "app_icon" in self.notif_dict:
            path = self.notif_dict["app_icon"].replace("file://", "")
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                size = int(self.config["card"]["icon-size"])
                pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(pixmap)
            else:
                self.icon_label.clear()

        if "summary" in self.notif_dict and self.notif_dict["summary"]:
            self.summary_label.setText(self.notif_dict["summary"])
        else:
            self.summary_label.clear()

        if "body" in self.notif_dict and self.notif_dict["body"]:
            self.body_label.setText(self.notif_dict["body"])
        else:
            self.body_label.clear()

        self.resize(self.sizeHint())
        self.update_position()

    def update_position(self):
        self.updateGeometry()
        offset_x = int(self.config["card"]["x-offset"])
        offset_y = int(self.config["card"]["y-offset"])
        card_width = int(self.config["card"]["width"])
        card_height = self.size().height()
        gap = int(self.config["card"]["gap"])
        stacking_direction = 1
        screen = self.app.primaryScreen()
        if offset_x < 0:
            offset_x = (screen.size().width() +
                offset_x -
                card_width)
        if offset_y < 0:
            offset_y = (screen.size().height() +
                offset_y -
                card_height)
            stacking_direction = -1
        for i in range(self.index):
            offset_y += (self.app.card_notifications[i].size().height() + gap) * stacking_direction
        self.setGeometry(
            offset_x,
            offset_y,
            card_width,
            card_height,
        )
        if len(self.app.card_notifications) > self.index+1:
            self.app.card_notifications[self.index+1].update_position()


    def close(self):
        if self in self.app.card_notifications:
            self.app.card_notifications.remove(self)
            for index in range(self.index, len(self.app.card_notifications)):
                self.app.card_notifications[index].index = index
            if len(self.app.card_notifications) > self.index:
                self.app.card_notifications[self.index].update_position()
        super().close()
