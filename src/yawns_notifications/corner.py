from yawns_notifications.base import BaseYawn

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
        self.adjust_size()
        self.update_position()
        self.next_update_position()

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
            
            self.move_to(m_geo.x() + rel_x, m_geo.y() + rel_y)
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

        self.move_to(offset_x, offset_y)
        
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
