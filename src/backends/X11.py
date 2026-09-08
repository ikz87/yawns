from PyQt5.QtCore import QThread, pyqtSignal
from Xlib import X
from Xlib.Xatom import ATOM, STRING
import Xlib.threaded
from PyQt5.QtX11Extras import QX11Info
from sys import path
path.append("../")
from yawns_notifications import BaseYawn

class FullscreenMonitor(QThread):
    """
    Monitors fullscreen windows and emits a signal when the state changes.
    """
    fullscreen_active = pyqtSignal(bool)

    def __init__(self, x11_display):
        super().__init__()
        self.display = x11_display

        self.root = self.display.screen().root

        self.NET_ACTIVE_WINDOW = self.display.intern_atom(
            "_NET_ACTIVE_WINDOW"
        )

        self.NET_WM_STATE = self.display.intern_atom(
            "_NET_WM_STATE"
        )

        self.NET_WM_STATE_FULLSCREEN = self.display.intern_atom(
            "_NET_WM_STATE_FULLSCREEN"
        )

        self.active_window = None
        self.last_state = None

    def get_active_window(self):
        prop = self.root.get_full_property(
            self.NET_ACTIVE_WINDOW,
            X.AnyPropertyType
        )

        if not prop or not prop.value:
            return None

        return self.display.create_resource_object(
            "window",
            prop.value[0]
        )

    def is_fullscreen(self, window):
        if window is None:
            return False

        try:
            prop = window.get_full_property(
                self.NET_WM_STATE,
                X.AnyPropertyType
            )

            if not prop:
                return False

            return self.NET_WM_STATE_FULLSCREEN in prop.value

        except Xlib.error.BadWindow:
            return False

    def update_active_window(self):
        window = self.get_active_window()

        if window is None:
            self.active_window = None
            self.update_state(False)
            return

        # Listen for _NET_WM_STATE changes on this window.
        try:
            window.change_attributes(
                event_mask=X.PropertyChangeMask
            )
        except Xlib.error.BadWindow:
            return

        self.active_window = window

        self.update_state(
            self.is_fullscreen(window)
        )

    def update_state(self, fullscreen):
        if fullscreen == self.last_state:
            return

        self.last_state = fullscreen
        self.fullscreen_active.emit(fullscreen)


    def run(self):
        # Watch root for active-window changes.
        self.root.change_attributes(
            event_mask=X.PropertyChangeMask
        )

        self.display.sync()

        # Initial state
        self.update_active_window()

        while not self.isInterruptionRequested():
            event = self.display.next_event()

            if event.type != X.PropertyNotify:
                continue

            # Active application changed
            if event.window == self.root:
                if event.atom == self.NET_ACTIVE_WINDOW:
                    self.update_active_window()

            # Current application's state changed
            elif (
                self.active_window is not None
                and event.window.id == self.active_window.id
            ):
                if event.atom == self.NET_WM_STATE:
                    self.update_state(
                        self.is_fullscreen(self.active_window)
                    )

            self.display.sync()

def setup_yawn_window(yawn: BaseYawn):
    """
    Set up X11 properties for a yawn.
    """
    urgency_struct = yawn.info_dict["hints"].get("urgency", None)
    yawn.urgency = 1
    if urgency_struct:
        yawn.urgency = int(urgency_struct.value)

    if QX11Info.isPlatformX11():
        # Use the previously open X display connection
        x11_display = yawn.app.display_info["X11_display"]

        x11_display.sync()

        # Get the window ID
        wid = int(yawn.winId())
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
        if yawn.urgency == 2:  # High urgency
            window.change_property(_NET_WM_STATE, ATOM, 32, [_NET_WM_STATE_ABOVE])
        else:  # Normal or low urgency
            window.change_property(_NET_WM_STATE, ATOM, 32, [])

        # Set _NET_WM_WINDOW_TYPE to both NOTIFICATION and UTILITY
        window.change_property(
            _NET_WM_WINDOW_TYPE, ATOM, 32, [_NET_WM_WINDOW_TYPE_NOTIFICATION]
        )

        # Set WM_CLASS
        window.change_property(WM_CLASS, STRING, 8, yawn.wm_class.encode("utf-8"))

        # Flush the display to apply changes
        x11_display.sync()
