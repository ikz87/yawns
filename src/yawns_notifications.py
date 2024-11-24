import os
from PyQt5.QtWidgets import QProgressBar, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget, QGridLayout, QLabel, QFrame
from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from enum import Enum
import time
from PyQt5.QtX11Extras import QX11Info
from  Xlib.display import Display
from Xlib.Xatom import STRING, ATOM
import Xlib
import dbus

class YawnType(Enum):
    CORNER = 1
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

    yawn_activated = pyqtSignal(int)

    def __init__(self, app, config, info_dict, parent=None):
        super().__init__(parent)
        self.app = app
        self.config = config
        self.info_dict = info_dict
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.close)

    def setup_widgets(self):
        """
        Setup the widgets for the yawn
        """
        yawn_class = type(self).__name__
        # Gotta use a QFrame to fill the whole widget
        # to allow bg transparency through QSS correctly
        self.main_container_layout = QVBoxLayout(self)
        self.main_container_layout.setContentsMargins(0,0,0,0)
        self.main_widget = QFrame()
        self.main_widget.setObjectName(yawn_class)
        self.main_container_layout.addWidget(self.main_widget)

        self.icon_label = QLabel()
        self.icon_label.setObjectName(yawn_class+"Icon")

        self.summary_label = QLabel()
        self.summary_label.setObjectName(yawn_class+"Summary")
        self.summary_label.setWordWrap(True)
        self.body_label = QLabel()
        self.body_label.setObjectName(yawn_class+"Body")
        self.body_label.setWordWrap(True)
        self.labels_layout = QVBoxLayout()
        self.labels_layout.setSpacing(0)
        self.labels_layout.addWidget(self.summary_label)
        self.labels_layout.addWidget(self.body_label)
        self.text_container = QFrame()
        self.text_container.setObjectName(yawn_class+"TextContainer")
        self.text_container.setLayout(self.labels_layout)

        self.bar = QProgressBar()
        self.bar.setObjectName(yawn_class+"Bar")
        self.bar.setTextVisible(False)
        self.bar.setMaximum(100)
        self.bar.setMinimum(0)


    def update_content(self):
        """
        Update the content of the yawn using its info_dict
        """
        # Start/Restart the timer
        if self.timer.isActive():
            self.timer.stop()
        timeout = int(self.config["timeout"])
        if "expire_timeout" in self.info_dict and int(self.info_dict["expire_timeout"]) > 0:
            timeout = int(self.info_dict["expire_timeout"])
        self.timer.setInterval(timeout)
        self.timer.start()

        # Below, no widget gets deleted or added.
        # if a info_dict has less content than expected,
        # then the empty widgets get "reset" and their
        # sizes are set to 0, 0
        if self.info_dict["hints"].get("icon_data", None):
            image_pixmap = QPixmap()
            if image_pixmap.loadFromData(self.info_dict["hints"]["icon_data"]):
                size = int(self.config["icon-size"])
                image_pixmap = image_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(image_pixmap)
                self.icon_label.setMinimumSize(0,0)
                self.icon_label.setMaximumSize(100000,100000)
            else:
                self.icon_label.clear()
                self.icon_label.setFixedSize(0,0)
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
        # TODO make labels wrap in between letters of words manually
        # because Qt doesn't provide that :(

        self.update_position()

    def update_position(self):
        pass

    def setup_x11_info(self):
        """
        Set up X11 properties for the window,
        based on the urgency of the noticiation.
        """
        urgency = int(self.info_dict["hints"]["urgency"].value)
        if QX11Info.isPlatformX11():
            # Open the X display connection
            x11_display = self.app.display

            x11_display.sync()

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
            window.change_property(WM_CLASS, STRING, 8, self.wm_class.encode("utf-8"))

            # Flush the display to apply changes
            x11_display.sync()


    def mousePressEvent(self, a0):
        """
        Handle mouse clicks on the notification
        """
        # One of the buttons here should "activate" the notification
        # But that is not working at all right now
        super().mousePressEvent(a0)
        if a0.button() == Qt.LeftButton:
            self.close()
        elif a0.button() == Qt.RightButton:
            pass
        elif a0.button() == Qt.MiddleButton:
            pass


class CornerYawn(BaseYawn):
    """
    The most classic notification design.
    Show a notification anchored to one of the corners of your screen.
    Multiple notifications stack vertically.
    """
    def __init__(self, app, config, info_dict, parent=None):
        super().__init__(app, config["corner"], info_dict, parent=parent)
        self.setFixedWidth(int(self.config["width"]))
        self.setMinimumHeight(int(self.config["height"]))
        self.index = len(app.corner_yawns)
        app.corner_yawns.append(self)

        # Set up window
        self.setWindowTitle("yawns - Corner")
        self.setCursor(Qt.PointingHandCursor)
        self.wm_class = "corner - yawn"
        self.setup_widgets()
        self.icon_label.setAlignment(Qt.AlignTop)
        self.summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.body_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.bar.setOrientation(Qt.Horizontal)
        self.text_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setSpacing(0)
        self.upper_layout = QHBoxLayout()
        self.upper_layout.setSpacing(0)
        self.main_layout.addStretch()
        self.main_layout.addLayout(self.upper_layout)

        self.main_layout.addWidget(self.bar)
        self.upper_layout.addWidget(self.icon_label)
        # We set stretch to make the label fill all the remaining space
        self.upper_layout.addWidget(self.text_container, stretch=1)

        self.upper_layout.addStretch()
        self.main_layout.addStretch()

        self.setup_x11_info()
        self.update_content()

    def update_position(self):
        """
        Update the position of the notification based on its size and config
        """
        offset_x = int(self.config["x-offset"])
        offset_y = int(self.config["y-offset"])
        corner_width = int(self.config["width"])
        corner_height = self.size().height()
        gap = int(self.config["gap"])
        stacking_direction = 1
        screen = self.app.primaryScreen()
        if offset_x < 0:
            offset_x = (screen.size().width() +
                offset_x -
                corner_width)
        if offset_y < 0:
            offset_y = (screen.size().height() +
                offset_y -
                corner_height)
            stacking_direction = -1
        for i in range(self.index):
            if self.app.corner_yawns[i].isVisible():
                offset_y += (self.app.corner_yawns[i].size().height() + gap) * stacking_direction
        self.move(offset_x, offset_y)
        if len(self.app.corner_yawns) > self.index+1:
            self.app.corner_yawns[self.index+1].update_position()

    def close(self):
        """
        Close widget and update the position the one
        stacked on it (if any).
        """
        if self in self.app.corner_yawns:
            self.app.corner_yawns.remove(self)
            for index in range(self.index, len(self.app.corner_yawns)):
                self.app.corner_yawns[index].index = index
            if len(self.app.corner_yawns) > self.index:
                self.app.corner_yawns[self.index].update_position()
        return super().close()


class CenterYawn(BaseYawn):
    """
    Show a notification in the center of the screen
    Multiple notifications stack vertically one behind the other.
    Meant mostly for displaying quick settings changes like
    volume, brightness or keyboard layout.
    """
    def __init__(self, app, config, info_dict, parent=None):
        super().__init__(app, config["center"], info_dict, parent=parent)

        self.index = len(app.center_yawns)
        app.center_yawns.append(self)

        # Set up window
        self.setWindowTitle("yawns - Center")
        self.wm_class = "center - yawn"
        self.setup_widgets()

        self.main_widget.setMinimumWidth(int(self.config["width"]))
        self.main_widget.setMaximumHeight(int(self.config["height"]))
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.body_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.body_label.setAlignment(Qt.AlignCenter)
        self.bar.setOrientation(Qt.Horizontal)

        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setSpacing(0)
        self.upper_layout = QHBoxLayout()
        self.upper_layout.setSpacing(0)

        self.main_layout.addWidget(self.icon_label, stretch=1)
        self.main_layout.addWidget(self.text_container, stretch=0)
        self.main_layout.addWidget(self.bar)

        self.setup_x11_info()
        self.update_content()

    def update_position(self):
        """
        Update the position of the notification based on its size and config
        """
        self_width = self.size().width()
        self_height = self.size().height()
        screen = self.app.primaryScreen()
        offset_x = int((screen.size().width() - self_width)/2)
        offset_y = int((screen.size().height() - self_height)/2)
        self.move(offset_x, offset_y)

    def close(self):
        """
        Close widget
        """
        if self in self.app.center_yawns:
            self.app.center_yawns.remove(self)
        return super().close()
