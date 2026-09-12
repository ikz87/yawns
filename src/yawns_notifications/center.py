from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QSizePolicy
from yawns_notifications.base import BaseYawn

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
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.body_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bar.setOrientation(Qt.Orientation.Horizontal)

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
