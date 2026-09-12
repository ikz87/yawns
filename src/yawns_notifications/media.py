import os
import subprocess
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QLabel,
    QFrame,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from yawns_notifications.base import BaseYawn

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
            # Uses CornerYawn index? Maintained as per original code
            self.index = len(app.yawn_arrays["CornerYawn"])
            app.yawn_arrays[self.yawn_class].append(self)
        else:
            self.index = -1

        self.setWindowTitle("yawns - Media")
        self.setup_widgets()
        self.setup_media_controls()
        self.setup_side_icon_layout()

        # Timer for rotating the icon
        self.icon_timer = QTimer()
        fps = int(self.config.get("fps", 30))
        self.icon_timer.setInterval(round(1000 / fps))
        self.icon_timer.timeout.connect(lambda: self.rotate_icon(5))
        self.result_pixmap = None
        self.angle = 0

        self.update_content()

    def _send_mpris_command(self, command):
        """Send an MPRIS command (Next, Previous, PlayPause) to the media player."""
        app_name = self.info_dict.get("app_name", "")
        # Build the MPRIS bus name from the app name
        bus_name = f"org.mpris.MediaPlayer2.{app_name.lower()}"
        try:
            subprocess.Popen(
                [
                    "dbus-send",
                    "--type=method_call",
                    "--dest=" + bus_name,
                    "/org/mpris/MediaPlayer2",
                    f"org.mpris.MediaPlayer2.Player.{command}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("dbus-send not found, cannot send MPRIS command")

    def update_buttons(self):
        """MediaYawns replace notification action buttons with media controls."""
        self.buttons_container.setFixedSize(0, 0)
        if hasattr(self, "media_controls_container"):
            show_buttons = self.config.get("show_buttons", "false") == "true"
            self.media_controls_container.setVisible(show_buttons)

    def _previous_clicked(self):
        self._send_mpris_command("Previous")
        self.restart_timer()

    def _play_pause_clicked(self):
        if self.is_playing:
            self._send_mpris_command("Pause")
            self.play_pause_button.setText("▶")
        else:
            self._send_mpris_command("Play")
            self.play_pause_button.setText("⏸")
        self.is_playing = not self.is_playing
        self.restart_timer()

    def _next_clicked(self):
        self._send_mpris_command("Next")
        self.restart_timer()

    def setup_media_controls(self):
        """Set up the 'Now playing...' header and media control buttons."""
        self.is_playing = True
        self.header_label = QLabel("Now playing...")
        self.header_label.setObjectName("MediaYawnHeader")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.media_controls_container = QFrame()
        self.media_controls_container.setObjectName("MediaYawnControls")
        self.media_controls_layout = QHBoxLayout(self.media_controls_container)
        self.media_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.media_controls_layout.setSpacing(0)

        self.prev_button = QPushButton("⏮")
        self.prev_button.setObjectName("MediaYawnControlButton")
        self.prev_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_button.clicked.connect(self._previous_clicked)

        self.play_pause_button = QPushButton("⏸")
        self.play_pause_button.setObjectName("MediaYawnControlButton")
        self.play_pause_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_pause_button.clicked.connect(self._play_pause_clicked)

        self.next_button = QPushButton("⏭")
        self.next_button.setObjectName("MediaYawnControlButton")
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.clicked.connect(self._next_clicked)

        for button in (self.prev_button, self.play_pause_button, self.next_button):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.media_controls_layout.addWidget(self.prev_button)
        self.media_controls_layout.addWidget(self.play_pause_button)
        self.media_controls_layout.addWidget(self.next_button)


    def setup_side_icon_layout(self):
        """Override to add header and media controls."""
        super().setup_side_icon_layout()
        self.header_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.media_controls_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.main_layout.insertWidget(0, self.header_label)
        self.main_layout.insertWidget(3, self.media_controls_container)

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
        rotated_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(rotated_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

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
        Update the spinning image on top of the vinyl icon_label.

        The vinyl is always rendered (and spins) even when no cover art is
        available; in that case only the bare vinyl is shown.
        """
        self.icon_size = int(self.config.get("icon-size", 64))

        rounded_pixmap = None
        img_bytes = self.info_dict.get("img_byte_arr", None)
        if img_bytes:
            image_pixmap = QPixmap()
            if image_pixmap.loadFromData(img_bytes):
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
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )

                # Create a rounded pixmap
                rounded_pixmap = QPixmap(scaled_size, scaled_size)
                rounded_pixmap.fill(Qt.GlobalColor.transparent)

                painter = QPainter(rounded_pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
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

        if vinyl_pixmap.isNull():
            self.result_pixmap = None
            self.icon_label.clear()
            self.icon_label.setFixedSize(0, 0)
            return

        vinyl_pixmap = vinyl_pixmap.scaled(
            self.icon_size,
            self.icon_size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.result_pixmap = QPixmap(vinyl_pixmap.size())
        self.result_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(self.result_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, vinyl_pixmap)

        if rounded_pixmap is not None:
            x = (vinyl_pixmap.width() - rounded_pixmap.width()) // 2
            y = (vinyl_pixmap.height() - rounded_pixmap.height()) // 2
            painter.drawPixmap(x, y, rounded_pixmap)
        painter.end()

        self.icon_label.setPixmap(self.result_pixmap)
        self.icon_label.setMinimumSize(0, 0)
        self.icon_label.setMaximumSize(100000, 100000)

        self.icon_timer.start()

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
