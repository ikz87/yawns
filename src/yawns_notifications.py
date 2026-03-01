import os
import cssutils
from PyQt5.QtWidgets import (
    QProgressBar,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QLabel,
    QFrame,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QPainterPath, QPixmap, QCursor
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
        self.setAttribute(Qt.WA_TranslucentBackground)
        
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
        if not self._should_clone():
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
        self.main_layout.update()
        self.updateGeometry()
        self.adjustSize()

    def update_position(self):
        pass

    def next_update_position(self):
        pass

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


class CornerYawn(BaseYawn):
    def __init__(
        self,
        app,
        config,
        info_dict,
        parent=None,
        _clone_for_screen=None,
        _primary=None,
    ):
        if "corner" in config:
            self.config = config["corner"]
        else:
            self.config = {}
        # Keep reference to full config for cloning
        self._full_config = config
        self.wm_class = "corner - yawn"
        super().__init__(
            app,
            config,
            info_dict,
            parent=parent,
            _clone_for_screen=_clone_for_screen,
            _primary=_primary,
        )
        self.setFixedWidth(int(self.config.get("width", 400)))
        self.setMaximumHeight(int(self.config.get("height", 500)))
        
        if not self.is_clone:
            self.index = len(app.yawn_arrays["CornerYawn"])
            app.yawn_arrays[self.yawn_class].append(self)
        else:
            self.index = -1

        self.setWindowTitle("yawns - Corner")
        self.setup_widgets()
        self.setup_side_icon_layout()
        self.update_content()

    def _create_clone(self, screen):
        return CornerYawn(
            self.app,
            self._full_config,
            self.info_dict,
            _clone_for_screen=screen,
            _primary=self,
        )

    def update_content(self):
        self.restart_timer()
        self.update_icon()

        layout_remaining_width = self.calculate_text_container_width(
            "#CornerYawn", "#CornerYawnIcon"
        )
        self.text_container.setFixedWidth(layout_remaining_width)

        self.update_text()
        self.update_bar()
        self.update_buttons()
        
        if not self.is_clone:
            self._update_clones()

    def update_position(self):
        # Mirror position from primary if this is a clone
        if self.is_clone and self.primary:
            p_screen = self.primary.get_target_screen()
            p_geo = p_screen.geometry()
            m_geo = self.get_target_screen().geometry()
            
            # Calculate relative position
            rel_x = self.primary.x() - p_geo.x()
            rel_y = self.primary.y() - p_geo.y()
            
            self.move(m_geo.x() + rel_x, m_geo.y() + rel_y)
            return

        offset_x = int(self.config.get("x-offset", -40))
        offset_y = int(self.config.get("y-offset", -40))
        corner_width = self.width()
        corner_height = self.height()
        gap = int(self.config.get("gap", 10))
        stacking_direction = 1
        screen = self.get_target_screen()
        geo = screen.geometry()

        if offset_x < 0:
            offset_x = geo.x() + geo.width() + offset_x - corner_width
        else:
            offset_x = geo.x() + offset_x

        if offset_y < 0:
            offset_y = geo.y() + geo.height() + offset_y - corner_height
            stacking_direction = -1
        else:
            offset_y = geo.y() + offset_y

        # Only count other PRIMARIES for stacking, not clones
        yawns_under_self = len(self.app.yawn_arrays["CornerYawn"]) - self.index - 1
        for i in range(yawns_under_self):
            if self.app.yawn_arrays["CornerYawn"][self.index + i + 1].isVisible():
                offset_y += (
                    self.app.yawn_arrays["CornerYawn"][self.index + i + 1].height()
                    + gap
                ) * stacking_direction

        self.move(offset_x, offset_y)
        
        # After moving, update clones
        if not self.is_clone:
            for clone in self.clones:
                clone.update_position()

    def next_update_position(self):
        if not self.is_clone and self.index > 0:
            self.app.yawn_arrays["CornerYawn"][self.index - 1].update_position()
            self.app.yawn_arrays["CornerYawn"][self.index - 1].next_update_position()

    def close(self):
        self._close_clones()
        if not self.is_clone and self in self.app.yawn_arrays["CornerYawn"]:
            self.app.yawn_arrays["CornerYawn"].remove(self)
            for index in range(len(self.app.yawn_arrays["CornerYawn"])):
                self.app.yawn_arrays["CornerYawn"][index].index = index
            if self.app.yawn_arrays["CornerYawn"]:
                self.app.yawn_arrays["CornerYawn"][-1].update_position()
                self.app.yawn_arrays["CornerYawn"][-1].next_update_position()
        return super().close()


class CenterYawn(BaseYawn):
    def __init__(
        self,
        app,
        config,
        info_dict,
        parent=None,
        _clone_for_screen=None,
        _primary=None,
    ):
        if "center" in config:
            self.config = config["center"]
        else:
            self.config = {}
        self._full_config = config
        self.wm_class = "center - yawn"
        super().__init__(
            app,
            config,
            info_dict,
            parent=parent,
            _clone_for_screen=_clone_for_screen,
            _primary=_primary,
        )

        if not self.is_clone:
            self.index = len(app.yawn_arrays["CenterYawn"])
            app.yawn_arrays[self.yawn_class].append(self)
        else:
            self.index = -1

        self.setWindowTitle("yawns - Center")
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

        self.update_content()

    def _create_clone(self, screen):
        return CenterYawn(
            self.app,
            self._full_config,
            self.info_dict,
            _clone_for_screen=screen,
            _primary=self,
        )

    def update_position(self):
        # CenterYawn doesn't need complex mirror logic, just center on target screen
        # super().update_position() # BaseYawn update_position does nothing
        self_width = self.size().width()
        self_height = self.size().height()
        screen = self.get_target_screen()
        geo = screen.geometry()
        offset_x = geo.x() + (geo.width() - self_width) // 2
        offset_y = geo.y() + (geo.height() - self_height) // 2
        self.move(offset_x, offset_y)
        
        if not self.is_clone:
            for clone in self.clones:
                clone.update_position()

    def close(self):
        self._close_clones()
        if not self.is_clone and self in self.app.yawn_arrays["CenterYawn"]:
            self.app.yawn_arrays["CenterYawn"].remove(self)
        return super().close()


class MediaYawn(BaseYawn):
    def __init__(
        self,
        app,
        config,
        info_dict,
        parent=None,
        _clone_for_screen=None,
        _primary=None,
    ):
        if "media" in config:
            self.config = config["media"]
        else:
            self.config = {}
        self._full_config = config
        self.wm_class = "media - yawn"
        super().__init__(
            app,
            config,
            info_dict,
            parent=parent,
            _clone_for_screen=_clone_for_screen,
            _primary=_primary,
        )
        self.setFixedWidth(int(self.config.get("width", 400)))
        self.setMaximumHeight(int(self.config.get("height", 500)))
        
        if not self.is_clone:
            self.index = len(app.yawn_arrays["CornerYawn"]) # Uses CornerYawn index? Maintained as per original code
            app.yawn_arrays[self.yawn_class].append(self)
        else:
            self.index = -1

        self.setWindowTitle("yawns - Media")
        self.setup_widgets()
        self.setup_side_icon_layout()

        # Timer for rotating the icon
        self.icon_timer = QTimer()
        fps = int(self.config.get("fps", 30))
        self.icon_timer.setInterval(round(1000 / fps))
        self.icon_timer.timeout.connect(lambda: self.rotate_icon(5))
        self.result_pixmap = None
        self.angle = 0

        self.update_content()

    def _create_clone(self, screen):
        return MediaYawn(
            self.app,
            self._full_config,
            self.info_dict,
            _clone_for_screen=screen,
            _primary=self,
        )

    def rotate_icon(self, angle_increment):
        if self.result_pixmap is None:
            return
        rotated_pixmap = QPixmap(self.result_pixmap.size())
        rotated_pixmap.fill(Qt.transparent)

        painter = QPainter(rotated_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        center = self.result_pixmap.rect().center()
        painter.translate(center.x() + 1, center.y() + 1)
        self.angle += angle_increment
        painter.rotate(self.angle)
        painter.translate(-center.x() - 1, -center.y() - 1)

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
                size = min(original_width, original_height)
                rect = (
                    (original_width - size) // 2,
                    (original_height - size) // 2,
                    size,
                    size,
                )
                image_pixmap = image_pixmap.copy(*rect)

                scaled_size = round(self.icon_size * 0.5)
                # Scale the cropped square
                image_pixmap = image_pixmap.scaled(
                    scaled_size,
                    scaled_size,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )

                # Create a rounded pixmap
                rounded_pixmap = QPixmap(scaled_size, scaled_size)
                rounded_pixmap.fill(Qt.transparent)

                painter = QPainter(rounded_pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                path = QPainterPath()
                path.addEllipse(0, 0, scaled_size, scaled_size)
                painter.setClipPath(path)
                painter.drawPixmap(0, 0, image_pixmap)
                painter.end()

                vinyl_path = "/usr/share/yawns/assets/vinyl.png"
                if self.config.get("bg_icon"):
                    vinyl_path = os.path.expanduser(self.config["bg_icon"])
                vinyl_pixmap = QPixmap()
                if not vinyl_pixmap.load(vinyl_path):
                    print(
                        f"Failed to load {vinyl_path} for a media yawn, defaulting to /usr/share/yawns/assets/vinyl.png"
                    )
                    vinyl_path = "/usr/share/yawns/assets/vinyl.png"
                    vinyl_pixmap.load(vinyl_path)

                vinyl_pixmap = vinyl_pixmap.scaled(
                    self.icon_size,
                    self.icon_size,
                    Qt.IgnoreAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.result_pixmap = QPixmap(vinyl_pixmap.size())
                self.result_pixmap.fill(Qt.transparent)

                painter = QPainter(self.result_pixmap)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.drawPixmap(0, 0, vinyl_pixmap)

                x = (vinyl_pixmap.width() - rounded_pixmap.width()) // 2
                y = (vinyl_pixmap.height() - rounded_pixmap.height()) // 2
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

        layout_remaining_width = self.calculate_text_container_width(
            "#MediaYawn", "#MediaYawnIcon"
        )
        self.text_container.setFixedWidth(layout_remaining_width)

        self.update_text()
        self.update_bar()
        self.update_buttons()
        
        if not self.is_clone:
            self._update_clones()

    def update_position(self):
        if self.is_clone and self.primary:
            p_screen = self.primary.get_target_screen()
            p_geo = p_screen.geometry()
            m_geo = self.get_target_screen().geometry()
            
            rel_x = self.primary.x() - p_geo.x()
            rel_y = self.primary.y() - p_geo.y()
            
            self.move(m_geo.x() + rel_x, m_geo.y() + rel_y)
            return

        offset_x = int(self.config.get("x-offset", 40))
        offset_y = int(self.config.get("y-offset", -40))
        corner_width = self.width()
        corner_height = self.height()
        screen = self.get_target_screen()
        geo = screen.geometry()

        if offset_x < 0:
            offset_x = geo.x() + geo.width() + offset_x - corner_width
        else:
            offset_x = geo.x() + offset_x

        if offset_y < 0:
            offset_y = geo.y() + geo.height() + offset_y - corner_height
        else:
            offset_y = geo.y() + offset_y

        self.move(offset_x, offset_y)
        
        if not self.is_clone:
            for clone in self.clones:
                clone.update_position()

    def close(self):
        self._close_clones()
        if not self.is_clone and self in self.app.yawn_arrays[self.yawn_class]:
            self.app.yawn_arrays[self.yawn_class].remove(self)
        return super().close()
