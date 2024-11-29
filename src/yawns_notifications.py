import os
import cssutils
from PyQt5.QtWidgets import (
    QProgressBar,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QGridLayout,
    QLabel,
    QFrame,
    QStyle,
)
from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from enum import Enum
import time
from PyQt5.QtX11Extras import QX11Info
from Xlib.display import Display
from Xlib.Xatom import STRING, ATOM
import Xlib
import dbus


class YawnType(Enum):
    CORNER = 1
    CENTER = 2


class BaseYawn(QWidget):
    """Base class for all notification widgets"""

    yawn_activated = pyqtSignal(int)

    def __init__(self, app, config, info_dict, parent=None):
        super().__init__(parent)
        if "general" in config:
            self.general_config = config["general"]
        else:
            self.general_config = {}

        self.app = app
        self.info_dict = info_dict
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(
            lambda: self.app.request_notification_closing.emit(
                self.info_dict["notification_id"], 1, self.info_dict["sender_id"]
            )
        )

    def setup_widgets(self):
        """
        Setup all needed widgets for the yawn
        """
        yawn_class = type(self).__name__
        # Gotta use a QFrame to fill the whole widget
        # to allow bg transparency through QSS correctly
        self.main_container_layout = QVBoxLayout(self)
        self.main_container_layout.setContentsMargins(0, 0, 0, 0)
        self.main_container_layout.setSpacing(0)
        self.main_widget = QFrame()
        self.main_widget.setObjectName(yawn_class)
        self.main_container_layout.addWidget(self.main_widget)

        self.icon_label = QLabel()
        self.icon_label.setObjectName(yawn_class + "Icon")

        self.summary_label = QLabel()
        self.summary_label.setObjectName(yawn_class + "Summary")
        self.summary_label.setWordWrap(True)
        self.body_label = QLabel()
        self.body_label.setObjectName(yawn_class + "Body")
        self.body_label.setWordWrap(True)
        self.labels_layout = QVBoxLayout()
        self.labels_layout.setContentsMargins(0, 0, 0, 0)
        self.labels_layout.setSpacing(0)
        self.labels_layout.addWidget(self.summary_label)
        self.labels_layout.addWidget(self.body_label)
        self.text_container = QFrame()
        self.text_container.setObjectName(yawn_class + "TextContainer")
        self.text_container.setLayout(self.labels_layout)

        self.bar = QProgressBar()
        self.bar.setObjectName(yawn_class + "Bar")
        self.bar.setTextVisible(False)
        self.bar.setMaximum(100)
        self.bar.setMinimum(0)

    def restart_timer(self):
        """
        Starts/Restarts the timer for closing the yawn.
        When a yawn gets replaced with another one,
        the timer gets reset with the updated timeout value
        """
        if self.timer.isActive():
            self.timer.stop()
        timeout = int(self.config.get("timeout", 5250))
        if (
            "expire_timeout" in self.info_dict
            and int(self.info_dict["expire_timeout"]) > 0
        ):
            timeout = int(self.info_dict["expire_timeout"])
        self.timer.setInterval(timeout)
        self.timer.start()

    def update_icon(self):
        """
        Updates the icon widget
        """
        self.icon_size = 0
        if self.info_dict["hints"].get("icon_data", None):
            image_pixmap = QPixmap()
            if image_pixmap.loadFromData(self.info_dict["hints"]["icon_data"]):
                self.icon_size = int(self.config.get("icon-size", 64))
                image_pixmap = image_pixmap.scaled(
                    self.icon_size,
                    self.icon_size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.icon_label.setPixmap(image_pixmap)
                self.icon_label.setMinimumSize(0, 0)
                self.icon_label.setMaximumSize(100000, 100000)
            else:
                self.icon_label.clear()
                self.icon_label.setFixedSize(0, 0)
        else:
            self.icon_label.clear()
            self.icon_label.setFixedSize(0, 0)

    def update_text(self):
        """
        Updates both the summary and body label
        """
        if "summary" in self.info_dict and self.info_dict["summary"]:
            text = self.info_dict["summary"].replace("\n", "<br>")
            self.summary_label.setText(text)
            self.summary_label.setMinimumSize(0, 0)
            self.summary_label.setMaximumSize(100000, 100000)
        else:
            self.summary_label.clear()
            self.summary_label.setFixedSize(0, 0)

        if "body" in self.info_dict and self.info_dict["body"]:
            text = self.info_dict["body"].replace("\n", "<br>")
            self.body_label.setText(text)
            self.body_label.setMinimumSize(0, 0)
            self.body_label.setMaximumSize(100000, 100000)
        else:
            self.body_label.clear()
            self.body_label.setFixedSize(0, 0)

    def update_bar(self):
        """
        Updates the bar widget
        """
        if "value" in self.info_dict["hints"] and self.info_dict["hints"]["value"]:
            value = int(self.info_dict["hints"]["value"].value)
            value = min(100, max(0, value))
            self.bar.setValue(value)
            self.bar.setMinimumSize(0, 0)
            self.bar.setMaximumSize(100000, 100000)
        else:
            self.bar.setValue(0)
            self.bar.setFixedSize(0, 0)

    def update_content(self):
        """
        Update the content of the yawn using its info_dict
        """
        self.restart_timer()

        # Below, no widget gets deleted or added.
        # if a info_dict has less content than expected,
        # then the empty widgets get "reset" and their
        # sizes are set to 0, 0
        self.update_icon()
        self.update_text()
        self.update_bar()

    def show(self):
        # We move the yawn to where it's supposed to be
        # before showing it
        self.adjust_size()
        self.update_position()
        super().show()
        self.next_update_position()

    def adjust_size(self):
        self.main_layout.update()
        self.updateGeometry()
        self.adjustSize()

    def update_position(self):
        pass

    def next_update_position(self):
        pass

    def setup_x11_info(self):
        """
        Set up X11 properties for the window,
        based on the urgency of the notification.
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
            WM_CLASS = x11_display.intern_atom("WM_CLASS")
            _NET_WM_STATE = x11_display.intern_atom("_NET_WM_STATE")
            _NET_WM_STATE_ABOVE = x11_display.intern_atom("_NET_WM_STATE_ABOVE")
            _NET_WM_WINDOW_TYPE = x11_display.intern_atom("_NET_WM_WINDOW_TYPE")
            _NET_WM_WINDOW_TYPE_NOTIFICATION = x11_display.intern_atom(
                "_NET_WM_WINDOW_TYPE_NOTIFICATION"
            )

            # Set _NET_WM_STATE to ABOVE for high urgency
            # (even though that doesn't actually work)
            if urgency == 2:  # High urgency
                window.change_property(_NET_WM_STATE, ATOM, 32, [_NET_WM_STATE_ABOVE])
            else:  # Normal or low urgency
                window.change_property(_NET_WM_STATE, ATOM, 32, [])

            # Set _NET_WM_WINDOW_TYPE to both NOTIFICATION and UTILITY
            window.change_property(
                _NET_WM_WINDOW_TYPE, ATOM, 32, [_NET_WM_WINDOW_TYPE_NOTIFICATION]
            )

            # Set WM_CLASS
            window.change_property(WM_CLASS, STRING, 8, self.wm_class.encode("utf-8"))

            # Flush the display to apply changes
            x11_display.sync()

    def mousePressEvent(self, a0):
        """
        Handle mouse clicks on the notification
        """
        super().mousePressEvent(a0)

        def do_actions(actions):
            if "activate" in actions:
                self.app.request_notification_activation.emit(self.info_dict)
            if "close" in actions:
                self.app.request_notification_closing.emit(
                    self.info_dict["notification_id"], 1, self.info_dict["sender_id"]
                )

        if a0.button() == Qt.LeftButton:
            do_actions(self.general_config.get("mouse-left-click", "activate close"))
        elif a0.button() == Qt.RightButton:
            do_actions(self.general_config.get("mouse-right-click", "close"))
        elif a0.button() == Qt.MiddleButton:
            do_actions(self.general_config.get("mouse-middle-click", "close"))
            pass


class CornerYawn(BaseYawn):
    """
    The most classic notification design.
    Show a notification anchored to one of the corners of your screen.
    Multiple notifications stack vertically.
    """

    def __init__(self, app, config, info_dict, parent=None):
        if "corner" in config:
            self.config = config["corner"]
        else:
            self.config = {}
        super().__init__(
            app, config, info_dict, parent=parent
        )
        self.setFixedWidth(int(self.config.get("width", 400)))
        self.setMaximumHeight(int(self.config.get("height", 500)))
        self.index = len(app.yawn_arrays["CornerYawn"])
        app.yawn_arrays["CornerYawn"].append(self)

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
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.upper_layout = QHBoxLayout()
        self.upper_layout.setContentsMargins(0, 0, 0, 0)
        self.upper_layout.setSpacing(0)
        self.main_layout.addLayout(self.upper_layout)

        self.icon_layout = QVBoxLayout()
        self.icon_layout.setContentsMargins(0, 0, 0, 0)
        self.icon_layout.setSpacing(0)
        self.icon_layout.addWidget(self.icon_label)
        self.icon_layout.addStretch()

        self.main_layout.addWidget(self.bar)
        self.upper_layout.addLayout(self.icon_layout)
        self.upper_layout.addWidget(self.text_container, stretch=1)

        self.setup_x11_info()
        self.update_content()

    def update_content(self):
        self.restart_timer()
        self.update_icon()
        # We gotta manually calculate how much space (width) the
        # text container should take up in the layout
        # because Qt kinda sucks and I'm starting to
        # realize it.

        # Parse the application stylesheet
        stylesheet = cssutils.parseString(self.app.stylesheet)

        # Helper function to expand shorthand properties
        def expand_shorthand(styles, property_name):
            if property_name in styles:
                values = styles[property_name].split()
                if len(values) == 1:  # All sides same
                    styles.update(
                        {
                            f"{property_name}-top": values[0],
                            f"{property_name}-right": values[0],
                            f"{property_name}-bottom": values[0],
                            f"{property_name}-left": values[0],
                        }
                    )
                elif len(values) == 2:  # Vertical | Horizontal
                    styles.update(
                        {
                            f"{property_name}-top": values[0],
                            f"{property_name}-bottom": values[0],
                            f"{property_name}-right": values[1],
                            f"{property_name}-left": values[1],
                        }
                    )
                elif len(values) == 3:  # Top | Horizontal | Bottom
                    styles.update(
                        {
                            f"{property_name}-top": values[0],
                            f"{property_name}-right": values[1],
                            f"{property_name}-left": values[1],
                            f"{property_name}-bottom": values[2],
                        }
                    )
                elif len(values) == 4:  # Top | Right | Bottom | Left
                    styles.update(
                        {
                            f"{property_name}-top": values[0],
                            f"{property_name}-right": values[1],
                            f"{property_name}-bottom": values[2],
                            f"{property_name}-left": values[3],
                        }
                    )
                del styles[property_name]
            return styles

        # Helper function to extract styles for a specific selector
        def get_styles(selector, properties):
            styles = {}
            for rule in stylesheet:
                if (
                    rule.type == rule.STYLE_RULE
                    and rule.selectorText.strip() == selector
                ):
                    for prop in rule.style:
                        if prop.name in properties or any(
                            prop.name.startswith(p) for p in properties
                        ):
                            styles[prop.name] = prop.value

            # Expand shorthand properties
            styles = expand_shorthand(styles, "margin")
            styles = expand_shorthand(styles, "padding")
            return styles

        # Extract relevant styles
        window_styles = get_styles("#CornerYawn", {"border", "margin", "padding"})
        icon_styles = get_styles("#CornerYawnIcon", {"border", "margin", "padding"})

        # Resolve shorthand and defaults for window styles
        window_border = int(
            window_styles.get("border", "0").split()[0].replace("px", "")
        )
        window_padding_left = int(
            window_styles.get("padding-left", "0").replace("px", "")
        )
        window_padding_right = int(
            window_styles.get("padding-right", "0").replace("px", "")
        )
        total_horizontal_window_padding = window_padding_left + window_padding_right

        # Resolve shorthand and defaults for icon styles
        icon_margin_left = int(icon_styles.get("margin-left", "0").replace("px", ""))
        icon_margin_right = int(icon_styles.get("margin-right", "0").replace("px", ""))
        icon_padding_left = int(icon_styles.get("padding-left", "0").replace("px", ""))
        icon_padding_right = int(
            icon_styles.get("padding-right", "0").replace("px", "")
        )
        icon_border = int(icon_styles.get("border", "0").split()[0].replace("px", ""))
        total_horizontal_icon_margin = (
            icon_margin_left
            + icon_margin_right
            + icon_padding_left
            + icon_padding_right
        )

        # Calculate layout width
        layout_remaining_width = (
            self.width()
            - 2 * window_border
            - total_horizontal_window_padding
            - self.icon_size
            + 2 * icon_border
            - (total_horizontal_icon_margin if self.icon_size else 0)
        )

        # Manually set the text container width so the label actually knows
        # how much it should expand
        self.text_container.setFixedWidth(layout_remaining_width)

        self.update_text()
        self.update_bar()

    def update_position(self):
        """
        Update the position of the notification based on its size and config
        """
        offset_x = int(self.config.get("x-offset", -40))
        offset_y = int(self.config.get("y-offset", -40))
        corner_width = self.width()
        corner_height = self.height()
        gap = int(self.config.get("gap", 10))
        stacking_direction = 1
        screen = self.app.primaryScreen()
        if offset_x < 0:
            offset_x = screen.size().width() + offset_x - corner_width
        if offset_y < 0:
            offset_y = screen.size().height() + offset_y - corner_height
            stacking_direction = -1
        yawns_under_self = len(self.app.yawn_arrays["CornerYawn"]) - self.index - 1
        for i in range(yawns_under_self):
            if self.app.yawn_arrays["CornerYawn"][self.index + i + 1].isVisible():
                offset_y += (
                    self.app.yawn_arrays["CornerYawn"][self.index + i + 1].height() + gap
                ) * stacking_direction
        self.move(offset_x, offset_y)

    def next_update_position(self):
        if self.index > 0:
            self.app.yawn_arrays["CornerYawn"][self.index - 1].update_position()
            self.app.yawn_arrays["CornerYawn"][self.index - 1].next_update_position()

    def close(self):
        """
        Close widget and update the position the one
        stacked on it (if any).
        """
        if self in self.app.yawn_arrays["CornerYawn"]:
            self.app.yawn_arrays["CornerYawn"].remove(self)
            for index in range(len(self.app.yawn_arrays["CornerYawn"])):
                self.app.yawn_arrays["CornerYawn"][index].index = index
            if self.app.yawn_arrays["CornerYawn"]:
                self.app.yawn_arrays["CornerYawn"][-1].update_position()
                self.app.yawn_arrays["CornerYawn"][-1].next_update_position()
        return super().close()


class CenterYawn(BaseYawn):
    """
    Show a notification in the center of the screen
    Multiple notifications stack vertically one behind the other.
    Meant mostly for displaying quick settings changes like
    volume, brightness or keyboard layout.
    """

    def __init__(self, app, config, info_dict, parent=None):
        if "center" in config:
            self.config = config["center"]
        else:
            self.config = {}
        super().__init__(
            app, config, info_dict, parent=parent
        )

        self.index = len(app.yawn_arrays["CenterYawn"])
        app.yawn_arrays["CenterYawn"].append(self)

        # Set up window
        self.setWindowTitle("yawns - Center")
        self.wm_class = "center - yawn"
        self.setup_widgets()

        self.main_widget.setMinimumWidth(int(self.config.get("width", 220)))
        self.main_widget.setMaximumHeight(int(self.config.get("height", 220)))
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.body_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.body_label.setAlignment(Qt.AlignCenter)
        self.bar.setOrientation(Qt.Horizontal)

        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setSpacing(0)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.main_layout.addWidget(self.icon_label, stretch=1)
        self.main_layout.addWidget(self.text_container, stretch=1)
        self.main_layout.addWidget(self.bar)

        self.setup_x11_info()
        self.update_content()

    def update_position(self):
        """
        Update the position of the notification based on its size and config
        """
        super().update_position()
        self_width = self.size().width()
        self_height = self.size().height()
        screen = self.app.primaryScreen()
        offset_x = int((screen.size().width() - self_width) / 2)
        offset_y = int((screen.size().height() - self_height) / 2)
        self.move(offset_x, offset_y)

    def close(self):
        """
        Close widget
        """
        if self in self.app.yawn_arrays["CenterYawn"]:
            self.app.yawn_arrays["CenterYawn"].remove(self)
        return super().close()
