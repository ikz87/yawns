import os
import cssutils
from PyQt5.QtWidgets import (
    QProgressBar,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QGridLayout,
    QLabel,
    QFrame,
    QStyle,
)
from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QPainterPath, QPixmap
from enum import Enum
import time
from PyQt5.QtX11Extras import QX11Info
from Xlib.display import Display
from Xlib.Xatom import STRING, ATOM
import Xlib
import dbus
from custom_widgets import SpinningImage


class YawnType(Enum):
    CORNER = 1
    CENTER = 2
    MEDIA = 3


class BaseYawn(QWidget):
    """Base class for all notification widgets"""

    yawn_activated = pyqtSignal(int)

    def __init__(self, app, config, info_dict, parent=None):
        super().__init__(parent)
        self.yawn_class = type(self).__name__
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
        # Gotta use a QFrame to fill the whole widget
        # to allow bg transparency through QSS correctly
        self.main_container_layout = QVBoxLayout(self)
        self.main_container_layout.setContentsMargins(0, 0, 0, 0)
        self.main_container_layout.setSpacing(0)
        self.main_widget = QFrame()
        self.main_widget.setObjectName(self.yawn_class)
        self.main_container_layout.addWidget(self.main_widget)

        self.icon_label = QLabel()
        self.icon_label.setObjectName(self.yawn_class + "Icon")

        self.summary_label = QLabel()
        self.summary_label.setObjectName(self.yawn_class + "Summary")
        self.summary_label.setWordWrap(True)
        self.body_label = QLabel()
        self.body_label.setObjectName(self.yawn_class + "Body")
        self.body_label.setWordWrap(True)
        self.labels_layout = QVBoxLayout()
        self.labels_layout.setContentsMargins(0, 0, 0, 0)
        self.labels_layout.setSpacing(0)
        self.labels_layout.addWidget(self.summary_label)
        self.labels_layout.addWidget(self.body_label)
        self.text_container = QFrame()
        self.text_container.setObjectName(self.yawn_class + "TextContainer")
        self.text_container.setLayout(self.labels_layout)

        self.bar = QProgressBar()
        self.bar.setObjectName(self.yawn_class + "Bar")
        self.bar.setTextVisible(False)
        self.bar.setMaximum(100)
        self.bar.setMinimum(0)

        self.buttons_container = QFrame()
        self.buttons_container.setObjectName(self.yawn_class + "ButtonsContainer")
        self.buttons_layout = QHBoxLayout(self.buttons_container)
        self.buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.buttons_layout.setSpacing(0)

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
        if self.info_dict.get("img_byte_arr", None):
            image_pixmap = QPixmap()
            if image_pixmap.loadFromData(self.info_dict["img_byte_arr"]):
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


    def update_buttons(self):
        """
        Updates the action buttons
        """
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

        # Delete the current buttons before adding the new ones
        empty_layout(self.buttons_layout)
        if ("actions" in self.info_dict
                and self.info_dict["actions"]
                and self.config.get("show_buttons", "false") == "true"
                ):
            actions = self.info_dict["actions"]
            for action_index in range(1,len(actions),2):
                action_text  = actions[action_index]
                action  = actions[action_index - 1]
                action_button = QPushButton(action_text)
                action_button.setCursor(Qt.PointingHandCursor)
                action_button.setObjectName(self.yawn_class+"ActionButton")
                action_button.clicked.connect(lambda _, act=action: self.action_clicked(act))
                self.buttons_layout.addWidget(action_button)
            close_button = QPushButton("Close")
            close_button.setObjectName(self.yawn_class+"CloseButton")
            close_button.setCursor(Qt.PointingHandCursor)
            close_button.clicked.connect(lambda: (
                self.app.request_notification_closing.emit(
                    self.info_dict["notification_id"], 1, self.info_dict["sender_id"]
                )))
            self.buttons_layout.addWidget(close_button)
        else:
            self.buttons_container.setFixedSize(0, 0)

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
        self.update_buttons()

    def action_clicked(self, action):
        """
        Called when an action button is clicked
        """
        self.app.request_notification_action.emit(
            self.info_dict["notification_id"],
            action,
            self.info_dict["sender_id"],
        )
        self.app.request_notification_closing.emit(
            self.info_dict["notification_id"], 1, self.info_dict["sender_id"]
        )


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
        urgency_struct = self.info_dict["hints"].get("urgency", None)
        self.urgency = 1
        if urgency_struct:
            self.urgency = int(urgency_struct.value)

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
            if self.urgency == 2:  # High urgency
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
            if "default" in actions:
                if "actions" in self.info_dict and self.info_dict["actions"]:
                    self.app.request_notification_action.emit(
                        self.info_dict["notification_id"],
                        self.info_dict["actions"][0],
                        self.info_dict["sender_id"],
                    )
                else:
                    print(f"No actions available for notification {self.info_dict["notification_id"]}")
            if "close" in actions:
                self.app.request_notification_closing.emit(
                    self.info_dict["notification_id"], 1, self.info_dict["sender_id"]
                )

        if a0.button() == Qt.LeftButton:
            do_actions(self.general_config.get("mouse-left-click", "close"))
        elif a0.button() == Qt.RightButton:
            do_actions(self.general_config.get("mouse-right-click", "close"))
        elif a0.button() == Qt.MiddleButton:
            do_actions(self.general_config.get("mouse-middle-click", "close"))
            pass


class CornerYawn(BaseYawn):
    """
    The most classic notification design.
    Shows up as a window anchored to one of the corners of your screen.
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
        app.yawn_arrays[self.yawn_class].append(self)

        # Set up window
        self.setWindowTitle("yawns - Corner")
        self.wm_class = "corner - yawn"
        self.setup_widgets()
        self.icon_label.setAlignment(Qt.AlignCenter)
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
        self.main_layout.addWidget(self.buttons_container, stretch=1)
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
        self.update_buttons()

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
        app.yawn_arrays[self.yawn_class].append(self)

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

class MediaYawn(BaseYawn):
    """
    The most classic notification design.
    Shows up as a window anchored to one of the corners of your screen.
    Multiple notifications stack vertically.
    """

    def __init__(self, app, config, info_dict, parent=None):
        if "media" in config:
            self.config = config["media"]
        else:
            self.config = {}
        super().__init__(
            app, config, info_dict, parent=parent
        )
        self.setFixedWidth(int(self.config.get("width", 400)))
        self.setMaximumHeight(int(self.config.get("height", 500)))
        self.index = len(app.yawn_arrays["CornerYawn"])
        app.yawn_arrays[self.yawn_class].append(self)

        # Set up window
        self.setWindowTitle("yawns - Media")
        self.wm_class = "media - yawn"
        self.setup_widgets()

        self.icon_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.body_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.bar.setOrientation(Qt.Horizontal)
        self.text_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        self.main_layout.addWidget(self.buttons_container, stretch=1)
        self.upper_layout.addLayout(self.icon_layout)
        self.upper_layout.addWidget(self.text_container, stretch=1)

        # Timer for rotating the icon
        self.icon_timer = QTimer()
        fps = int(self.config.get("fps", 30))
        self.icon_timer.setInterval(round(1000/fps))
        self.icon_timer.timeout.connect(lambda: self.rotate_icon(5))
        self.result_pixmap = None
        self.angle = 0

        self.setup_x11_info()
        self.update_content()

    def rotate_icon(self, angle_increment):
        """
        Rotates the pixmap displayed on self.icon_label by the given angle.

        :param angle: The angle in degrees to rotate the pixmap.
        """
        if self.result_pixmap is None:
            return  # Safeguard in case no pixmap is set
        # Create a new pixmap of the same size as the original
        rotated_pixmap = QPixmap(self.result_pixmap.size())
        rotated_pixmap.fill(Qt.transparent)  # Fill with transparent background

        # Use QPainter to rotate the pixmap
        painter = QPainter(rotated_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Translate to the center of the pixmap, rotate, and then draw the original pixmap
        center = self.result_pixmap.rect().center()
        painter.translate(center)
        self.angle += angle_increment
        painter.rotate(self.angle)
        painter.translate(-center)

        # Draw the original pixmap
        painter.drawPixmap(0, 0, self.result_pixmap)
        
        painter.end()
        self.icon_label.setPixmap(rotated_pixmap)


    def update_icon(self):
        """
        Update the spinning image on top of the vynil icon_label
        """
        self.icon_size = 0
        if self.info_dict.get("img_byte_arr", None):
            image_pixmap = QPixmap()
            if image_pixmap.loadFromData(self.info_dict["img_byte_arr"]):
                self.icon_size = int(self.config.get("icon-size", 64))
                # Crop the image to a square
                original_width = image_pixmap.width()
                original_height = image_pixmap.height()
                size = min(original_width, original_height)  # Largest square size
                rect = (
                    (original_width - size) // 2,
                    (original_height - size) // 2,
                    size,
                    size,
                )
                image_pixmap = image_pixmap.copy(*rect)

                scaled_size = round(self.icon_size*0.5)
                # Scale the cropped square
                image_pixmap = image_pixmap.scaled(
                    scaled_size,
                    scaled_size,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )

                # Create a rounded pixmap
                rounded_pixmap = QPixmap(scaled_size, scaled_size)
                rounded_pixmap.fill(Qt.transparent)  # Transparent background

                # Draw the rounded pixmap
                painter = QPainter(rounded_pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                path = QPainterPath()
                path.addEllipse(0, 0, scaled_size, scaled_size)  # Circle bounds
                painter.setClipPath(path)
                painter.drawPixmap(0, 0, image_pixmap)
                painter.end()

                vinyl_pixmap = QPixmap()
                vinyl_pixmap.load("/usr/share/yawns/assets/vinyl.png")
                vinyl_pixmap = vinyl_pixmap.scaled(
                    self.icon_size,
                    self.icon_size,
                    Qt.IgnoreAspectRatio,
                    Qt.SmoothTransformation,
                )
                # Create a new QPixmap the same size as the background
                self.result_pixmap = QPixmap(vinyl_pixmap.size())
                self.result_pixmap.fill(Qt.transparent)  # Ensure the pixmap starts transparent

                # Create a QPainter to draw the images
                painter = QPainter(self.result_pixmap)
                painter.setRenderHint(QPainter.Antialiasing)

                # Draw the background
                painter.drawPixmap(0, 0, vinyl_pixmap)

                # Determine the position for the overlay
                x = (vinyl_pixmap.width() - rounded_pixmap.width()) // 2
                y = (vinyl_pixmap.height() - rounded_pixmap.height()) // 2

                # Draw the overlay
                painter.drawPixmap(x, y, rounded_pixmap)
                painter.end()
                self.icon_label.setPixmap(self.result_pixmap)
                self.icon_label.setMinimumSize(0, 0)
                self.icon_label.setMaximumSize(100000, 100000)

                self.icon_timer.start()
            else:
                self.result_pixmap = None
                self.icon_label.clear()
                self.icon_label.setFixedSize(0, 0)
        else:
            self.result_pixmap = None
            self.icon_label.clear()
            self.icon_label.setFixedSize(0, 0)

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
        window_styles = get_styles("#MediaYawn", {"border", "margin", "padding"})
        icon_styles = get_styles("#MediaYawnIcon", {"border", "margin", "padding"})

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
        self.update_buttons()

    def update_position(self):
        """
        Update the position of the notification based on its size and config
        """
        offset_x = int(self.config.get("x-offset", 40))
        offset_y = int(self.config.get("y-offset", -40))
        corner_width = self.width()
        corner_height = self.height()
        screen = self.app.primaryScreen()
        if offset_x < 0:
            offset_x = screen.size().width() + offset_x - corner_width
        if offset_y < 0:
            offset_y = screen.size().height() + offset_y - corner_height
        self.move(offset_x, offset_y)

    def close(self):
        """
        Close widget and update the position the one
        stacked on it (if any).
        """
        if self in self.app.yawn_arrays[self.yawn_class]:
            self.app.yawn_arrays[self.yawn_class].remove(self)
        return super().close()
