import os
from PyQt5.QtWidgets import QProgressBar, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget, QGridLayout, QLabel, QFrame
from PyQt5.QtCore import QSize, Qt, QTimer
from PyQt5.QtGui import QPixmap
from enum import Enum
import time
from PyQt5.QtX11Extras import QX11Info
from  Xlib.display import Display
from Xlib.Xatom import STRING, ATOM
import Xlib


class YawnType(Enum):
    CARD = 1
    CENTER = 2

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


class BaseYawn(QWidget):
    """ Base class for all notification widgets """
    def __init__(self, config, info_dict, parent=None):
        super().__init__(parent)
        #self.setWindowFlags(Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.info_dict = info_dict
        timeout = int(config["general"]["timeout"])
        if "expire_timeout" in info_dict and int(info_dict["expire_timeout"]) > 0:
            timeout = int(info_dict["expire_timeout"])
        self.timer = QTimer(self)
        self.timer.setInterval(timeout)
        self.timer.timeout.connect(self.close)
        self.timer.start()


class CardYawn(BaseYawn):
    """
    The most classic notification design.
    Show a card anchored to one of the corners of your screen.
    Multiple notifications stack vertically.
    """
    def __init__(self, app, config, info_dict, parent=None):
        super().__init__(config, info_dict, parent=parent)
        self.app = app
        self.info_dict = info_dict
        self.config = config
        self.setFixedWidth(int(config["card"]["width"]))
        self.setMinimumHeight(int(config["card"]["height"]))
        self.index = len(app.card_yawns)
        app.card_yawns.append(self)

        # Set up window
        self.setWindowTitle("yawns - Card")

        # Set up content
        # Gotta use a QFrame to fill the whole widget
        # to allow bg transparency through QSS correctly
        self.container_layout = QVBoxLayout(self)
        self.container_layout.setContentsMargins(0,0,0,0)
        self.main_widget = QFrame()
        self.main_widget.setObjectName("CardYawn")
        self.container_layout.addWidget(self.main_widget)

        self.main_layout = QVBoxLayout(self.main_widget)
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
        self.icon_label.setAlignment(Qt.AlignTop)
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
        # We set stretch to make the label fill all the remaining space
        self.upper_layout.addWidget(self.text_container, stretch=1)
        self.labels_layout.addWidget(self.summary_label)
        self.labels_layout.addWidget(self.body_label)

        self.upper_layout.addStretch()
        self.main_layout.addStretch()

        self.setup_x11_info()
        self.update_content()

    def setup_x11_info(self):
        urgency = int(self.info_dict["hints"]["urgency"].value)
        if QX11Info.isPlatformX11():
            # Open the X display connection
            x11_display = self.app.display

            # Get the window ID
            wid = int(self.winId())
            window = x11_display.create_resource_object("window", wid)

            # Get atoms for the required properties
            WM_CLASS = x11_display.intern_atom('WM_CLASS')
            _NET_WM_STATE = x11_display.intern_atom('_NET_WM_STATE')
            _NET_WM_STATE_ABOVE = x11_display.intern_atom('_NET_WM_STATE_ABOVE')
            _NET_WM_WINDOW_TYPE = x11_display.intern_atom('_NET_WM_WINDOW_TYPE')
            _NET_WM_WINDOW_TYPE_NOTIFICATION = x11_display.intern_atom('_NET_WM_WINDOW_TYPE_NOTIFICATION')
            _NET_WM_WINDOW_TYPE_UTILITY = x11_display.intern_atom('_NET_WM_WINDOW_TYPE_UTILITY')

            # Set _NET_WM_STATE to ABOVE for high urgency
            # (even though that doesn't actually work)
            if urgency == 2:  # High urgency
                window.change_property(_NET_WM_STATE, ATOM, 32, [_NET_WM_STATE_ABOVE])
            else:  # Normal or low urgency
                window.change_property(_NET_WM_STATE, ATOM, 32, [])

            # Set _NET_WM_WINDOW_TYPE to both NOTIFICATION and UTILITY
            window.change_property(_NET_WM_WINDOW_TYPE, ATOM, 32, [
                _NET_WM_WINDOW_TYPE_NOTIFICATION, _NET_WM_WINDOW_TYPE_UTILITY
            ])

            # Set WM_CLASS
            window.change_property(WM_CLASS, STRING, 8, b"card-yawn")

            # Flush the display to apply changes
            x11_display.flush()


    def update_content(self):
        """
        Update the content of the noticiation using self.info_dict
        """
        # Restart the timer
        self.timer.stop()
        self.timer.start()

        # Below, no widget gets deleted or added.
        # if a info_dict has less content than expected,
        # then the empty widgets get "reset" and their
        # sizes are set to 0, 0

        # Handle the hint "image_path" but also use "app_icon" as a fallback icon
        image_path = ""
        app_icon = ""
        if "image_path" in self.info_dict["hints"]:
            image_path = self.info_dict["hints"]["image_path"].value.replace("file://", "")
        if "app_icon" in self.info_dict and self.info_dict["app_icon"]:
            app_icon = self.info_dict["app_icon"].replace("file://", "")
        image_pixmap = QPixmap(image_path)
        app_pixmap = QPixmap(app_icon)
        if not image_pixmap.isNull():
            size = int(self.config["card"]["icon-size"])
            image_pixmap = image_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.icon_label.setPixmap(image_pixmap)
            self.icon_label.setMinimumSize(0,0)
            self.icon_label.setMaximumSize(100000,100000)
        elif not app_pixmap.isNull():
            size = int(self.config["card"]["icon-size"])
            app_pixmap = app_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.icon_label.setPixmap(app_pixmap)
            self.icon_label.setMinimumSize(0,0)
            self.icon_label.setMaximumSize(100000,100000)
        else:
            self.icon_label.clear()
            self.icon_label.setFixedSize(0,0)

        if "summary" in self.info_dict and self.info_dict["summary"]:
            self.summary_label.setText(self.info_dict["summary"])
            self.summary_label.setMinimumSize(0,0)
            self.summary_label.setMaximumSize(100000,100000)
        else:
            self.summary_label.clear()
            self.summary_label.setFixedSize(0,0)

        if "body" in self.info_dict and self.info_dict["body"]:
            self.body_label.setText(self.info_dict["body"])
            self.body_label.setMinimumSize(0,0)
            self.body_label.setMaximumSize(100000,100000)
        else:
            self.body_label.clear()
            self.body_label.setFixedSize(0,0)

        if "value" in self.info_dict["hints"] and self.info_dict["hints"]["value"]:
            value = int(self.info_dict["hints"]["value"].value)
            value = min(100,max(0,value))
            self.bar.setValue(value)
            self.bar.setMinimumSize(0,0)
            self.bar.setMaximumSize(100000,100000)
        else:
            self.bar.setValue(0)
            self.bar.setFixedSize(0,0)

        self.main_layout.update()
        self.updateGeometry()
        self.setMinimumHeight(0)
        self.resize(self.sizeHint())
        if self.size().height() > int(self.config["card"]["height"]):
            self.setFixedHeight(int(self.config["card"]["height"]))

        # TODO make labels wrap in between letters of words manually
        # because Qt doesn't provide that :(

        self.update_position()

    def update_position(self):
        """
        Update the position of the notification based on its size and config
        """
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
            if self.app.card_yawns[i].isVisible():
                offset_y += (self.app.card_yawns[i].size().height() + gap) * stacking_direction
        self.move(offset_x, offset_y)
        if len(self.app.card_yawns) > self.index+1:
            self.app.card_yawns[self.index+1].update_position()


    def close(self):
        """
        Close widget and update the position the one
        stacked on it (if any).
        """
        if self in self.app.card_yawns:
            self.app.card_yawns.remove(self)
            for index in range(self.index, len(self.app.card_yawns)):
                self.app.card_yawns[index].index = index
            if len(self.app.card_yawns) > self.index:
                self.app.card_yawns[self.index].update_position()
        super().close()
