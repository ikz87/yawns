import os
import cssutils
from PyQt6.QtWidgets import (
    QProgressBar,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QLabel,
    QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from enum import Enum

class YawnType(Enum):
    CORNER = 1
    CENTER = 2
    MEDIA = 3

class BaseYawn(QWidget):
    """Base class for all notification widgets"""

    yawn_activated = pyqtSignal(int)

    def __init__(
        self,
        app,
        config,
        info_dict,
        parent=None,
        _clone_for_screen=None,
        _primary=None,
    ):
        super().__init__(parent)
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        if not getattr(app, "is_wayland", False):
            # X11 only: bypass the window manager. On Wayland the layer surface
            # handles stacking/placement, so this hint is meaningless there.
            flags |= Qt.WindowType.X11BypassWindowManagerHint
        self.setWindowFlags(flags)
        self.yawn_class = type(self).__name__
        
        # Clone logic setup
        self._clone_for_screen = _clone_for_screen
        self.is_clone = _clone_for_screen is not None
        self.primary = _primary
        self.clones = []

        if "general" in config:
            self.general_config = config["general"]
        else:
            self.general_config = {}

        self.app = app
        self.info_dict = info_dict
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Only the primary yawn manages the close timer
        if not self.is_clone:
            self.timer = QTimer(self)
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(
                lambda: self.app.request_notification_closing.emit(
                    self.info_dict["notification_id"], 1, self.info_dict["sender_id"]
                )
            )
        else:
            self.timer = None

        urgency_struct = self.info_dict["hints"].get("urgency", None)
        self.urgency = 1
        if urgency_struct:
            self.urgency = int(urgency_struct.value)

        self.app.setup_yawn_window(self)

    def get_target_screen(self):
        """Resolve which QScreen to use based on config or clone status."""
        # If this is a clone, it is assigned a specific screen
        if self._clone_for_screen:
            return self._clone_for_screen

        monitor = self.config.get("monitor", "primary")
        screens = self.app.screens()

        # If configured for "all" or "-1", the PRIMARY yawn goes to the primary screen.
        # Clones will be spawned for the others.
        if str(monitor).lower() in ["all", "-1"]:
            return self.app.primaryScreen()

        if monitor == "focused":
            cursor_pos = QCursor.pos()
            for s in screens:
                if s.geometry().contains(cursor_pos):
                    return s
            return self.app.primaryScreen()

        if monitor == "primary":
            return self.app.primaryScreen()

        try:
            idx = int(monitor)
            if 0 <= idx < len(screens):
                return screens[idx]
            print(f"Monitor index {idx} out of range, falling back to primary")
        except ValueError:
            print(f"Invalid monitor value '{monitor}', falling back to primary")

        return self.app.primaryScreen()

    def _should_clone(self):
        """Check if we should spawn clones."""
        monitor = str(self.config.get("monitor", "primary")).lower()
        return not self.is_clone and monitor in ["all", "-1"]

    def _spawn_clones(self):
        """Create clones for all other screens."""
        if not self._should_clone() or self.clones:
            return
        
        primary_screen = self.get_target_screen()
        for screen in self.app.screens():
            if screen != primary_screen:
                try:
                    clone = self._create_clone(screen)
                    self.clones.append(clone)
                    clone.show()
                except NotImplementedError:
                    print(f"Cloning not implemented for {self.yawn_class}")

    def _create_clone(self, screen):
        """Factory method to be implemented by subclasses."""
        raise NotImplementedError

    def _update_clones(self):
        """Propagate content updates to clones."""
        for clone in self.clones:
            clone.info_dict = self.info_dict
            clone.update_content()
            
    def _close_clones(self):
        """Close all associated clones."""
        for clone in self.clones:
            clone.close()
        self.clones.clear()

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

    def setup_side_icon_layout(self):
        """
        Sets up the common layout used by CornerYawn and MediaYawn:
        """
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.body_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.bar.setOrientation(Qt.Orientation.Horizontal)
        self.text_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

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

    def restart_timer(self):
        """
        Starts/Restarts the timer for closing the yawn.
        """
        if self.is_clone:
            return

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
            from PyQt6.QtGui import QPixmap
            image_pixmap = QPixmap()
            if image_pixmap.loadFromData(self.info_dict["img_byte_arr"]):
                self.icon_size = int(self.config.get("icon-size", 64))
                image_pixmap = image_pixmap.scaled(
                    self.icon_size,
                    self.icon_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
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
        if (
            "actions" in self.info_dict
            and self.info_dict["actions"]
            and self.config.get("show_buttons", "false") == "true"
        ):
            actions = self.info_dict["actions"]
            for action_index in range(1, len(actions), 2):
                action_text = actions[action_index]
                action = actions[action_index - 1]
                action_button = QPushButton(action_text)
                action_button.setCursor(Qt.PointingHandCursor)
                action_button.setObjectName(self.yawn_class + "ActionButton")
                action_button.clicked.connect(
                    lambda _, act=action: self.action_clicked(act)
                )
                self.buttons_layout.addWidget(action_button)
            close_button = QPushButton("Close")
            close_button.setObjectName(self.yawn_class + "CloseButton")
            close_button.setCursor(Qt.PointingHandCursor)
            close_button.clicked.connect(
                lambda: (
                    self.app.request_notification_closing.emit(
                        self.info_dict["notification_id"],
                        1,
                        self.info_dict["sender_id"],
                    )
                )
            )
            self.buttons_layout.addWidget(close_button)
        else:
            self.buttons_container.setFixedSize(0, 0)

    def calculate_text_container_width(self, window_selector, icon_selector):
        """
        Calculates the available width for the text container by parsing the
        stylesheet.
        """
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

        def px(val):
            return int(val.replace("px", "")) if val else 0

        # Extract relevant styles
        window_styles = get_styles(window_selector, {"border", "margin", "padding"})
        icon_styles = get_styles(icon_selector, {"border", "margin", "padding"})

        # Resolve shorthand and defaults for window styles
        window_border = px(window_styles.get("border", "0").split()[0])
        window_padding_left = px(window_styles.get("padding-left", "0"))
        window_padding_right = px(window_styles.get("padding-right", "0"))
        total_horizontal_window_padding = window_padding_left + window_padding_right

        # Resolve shorthand and defaults for icon styles
        icon_margin_left = px(icon_styles.get("margin-left", "0"))
        icon_margin_right = px(icon_styles.get("margin-right", "0"))
        icon_padding_left = px(icon_styles.get("padding-left", "0"))
        icon_padding_right = px(icon_styles.get("padding-right", "0"))
        icon_border = px(icon_styles.get("border", "0").split()[0])

        total_horizontal_icon_margin = (
            icon_margin_left
            + icon_margin_right
            + icon_padding_left
            + icon_padding_right
        )

        # Calculate layout width
        return (
            self.width()
            - 2 * window_border
            - total_horizontal_window_padding
            - self.icon_size
            + 2 * icon_border
            - (total_horizontal_icon_margin if self.icon_size else 0)
        )

    def update_content(self):
        """
        Update the content of the yawn using its info_dict
        """
        self.restart_timer()
        self.update_icon()
        self.update_text()
        self.update_bar()
        self.update_buttons()
        self.adjust_size()
        self.update_position()
        self.next_update_position()
        if not self.is_clone:
            self._update_clones()

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
        self.adjust_size()
        self.update_position()
        super().show()
        self.next_update_position()
        if not self.is_clone:
            self._spawn_clones()

    def adjust_size(self):
        self.summary_label.adjustSize()
        self.body_label.adjustSize()
        self.text_container.adjustSize()
        if hasattr(self, "header_label"):
            self.header_label.adjustSize()
        if hasattr(self, "media_controls_container"):
            self.media_controls_container.adjustSize()
        if hasattr(self, "buttons_container"):
            self.buttons_container.adjustSize()
        self.main_widget.resize(self.main_widget.width(), 0)
        self.main_widget.adjustSize()
        self.resize(self.width(), 0)
        self.adjustSize()

    def update_position(self):
        pass

    def next_update_position(self):
        pass

    def move_to(self, x, y):
        """
        Position the yawn at absolute global coordinates.

        On X11 this is a plain window move. On Wayland an xdg_toplevel cannot
        be moved by the client, so the absolute position is translated into
        layer-shell anchors + margins and applied by the native backend.
        """
        if getattr(self.app, "is_wayland", False):
            self._wayland_set_geometry(x, y)
        else:
            self.move(x, y)

    def _wayland_set_geometry(self, x, y):
        from backends import Wayland as wayland

        pointer = getattr(self, "_wayland_window_ptr", None)
        if pointer is None:
            return

        geo = self.get_target_screen().geometry()
        width, height = self.width(), self.height()

        # Anchor to the nearest screen edges. The surface is then positioned
        # with margins relative to those edges.
        left = (x + width / 2.0) < (geo.x() + geo.width() / 2.0)
        top = (y + height / 2.0) < (geo.y() + geo.height() / 2.0)

        anchor = (wayland.ANCHOR_LEFT if left else wayland.ANCHOR_RIGHT) | (
            wayland.ANCHOR_TOP if top else wayland.ANCHOR_BOTTOM
        )
        margin_top = int(y - geo.y()) if top else 0
        margin_bottom = int((geo.y() + geo.height()) - (y + height)) if not top else 0
        margin_left = int(x - geo.x()) if left else 0
        margin_right = int((geo.x() + geo.width()) - (x + width)) if not left else 0

        wayland.set_geometry(
            pointer,
            anchor,
            margin_top,
            margin_right,
            margin_bottom,
            margin_left,
            int(width),
            int(height),
        )

    def mousePressEvent(self, a0):
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
                    print(
                        f"No actions available for notification {self.info_dict['notification_id']}"
                    )
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
