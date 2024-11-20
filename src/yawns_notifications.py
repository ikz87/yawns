from PyQt5.QtWidgets import QProgressBar, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget, QGridLayout, QLabel, QFrame
from PyQt5.QtCore import QSize, Qt, QTimer
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
        self.main_layout.setSpacing(0)
        self.upper_layout = QHBoxLayout()
        self.upper_layout.setSpacing(0)
        self.labels_layout = QVBoxLayout()
        self.labels_layout.setSpacing(0)
        self.main_layout.addStretch()
        self.main_layout.addLayout(self.upper_layout)

        self.text_container = QFrame()
        self.text_container.setObjectName("CardTextContainer")
        self.text_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.text_container.setLayout(self.labels_layout)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("CardIcon")


        self.summary_label = QLabel()
        self.summary_label.setObjectName("CardSummary")
        self.summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.summary_label.setWordWrap(True)

        self.body_label = QLabel()
        self.body_label.setObjectName("CardBody")
        self.body_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.body_label.setWordWrap(True)

        self.bar = QProgressBar()
        self.bar.setObjectName("CardBar")
        self.bar.setTextVisible(False)
        self.bar.setOrientation(Qt.Horizontal)
        self.bar.setMaximum(100)
        self.bar.setMinimum(0)

        self.main_layout.addWidget(self.bar)
        self.upper_layout.addWidget(self.icon_label)
        self.upper_layout.addWidget(self.text_container, stretch=1)
        self.labels_layout.addWidget(self.summary_label)
        self.labels_layout.addWidget(self.body_label)

        self.upper_layout.addStretch()
        self.main_layout.addStretch()

        self.update_content()

    def update_content(self):
        # Restart the timer
        self.timer.stop()
        self.timer.start()

        if "image_path" in self.notif_dict["hints"]:
            path = self.notif_dict["hints"]["image_path"].value.replace("file://", "")
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                size = int(self.config["card"]["icon-size"])
                pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(pixmap)
            else:
                self.icon_label.clear()

        elif "app_icon" in self.notif_dict and self.notif_dict["app_icon"]:
            path = self.notif_dict["app_icon"].replace("file://", "")
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                size = int(self.config["card"]["icon-size"])
                pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(pixmap)
                self.icon_label.setMinimumSize(0,0)
                self.icon_label.setMaximumSize(10000,10000)
            else:
                self.icon_label.clear()
                self.icon_label.setFixedSize(0,0)
        else:
            self.icon_label.clear()
            self.icon_label.setFixedSize(0,0)

        if "summary" in self.notif_dict and self.notif_dict["summary"]:
            self.summary_label.setText(self.notif_dict["summary"])
            self.summary_label.setMinimumSize(0,0)
            self.summary_label.setMaximumSize(10000,10000)
        else:
            self.summary_label.clear()
            self.summary_label.setFixedSize(0,0)

        if "body" in self.notif_dict and self.notif_dict["body"]:
            self.body_label.setText(self.notif_dict["body"])
            self.body_label.setMinimumSize(0,0)
            self.body_label.setMaximumSize(10000,10000)
        else:
            self.body_label.clear()
            self.body_label.setFixedSize(0,0)

        if "value" in self.notif_dict["hints"] and self.notif_dict["hints"]["value"]:
            value = int(self.notif_dict["hints"]["value"].value)
            value = min(100,max(0,value))
            self.bar.setValue(value)
            self.bar.setMinimumSize(0,0)
            self.bar.setMaximumSize(10000,10000)
        else:
            self.bar.setValue(0)
            self.bar.setFixedSize(0,0)

        self.main_layout.update()
        self.updateGeometry()
        self.resize(self.sizeHint())

        #TODO make labels wrap in between letters of words

        self.update_position()

    def update_position(self):
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
        self.move(offset_x, offset_y)
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
