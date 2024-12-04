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

    def run(self):
        root = self.display.screen().root
        screen = self.display.screen()

        # Select the events you want to listen to for the root window
        root.change_attributes(event_mask=X.FocusChangeMask | X.PropertyChangeMask)
        self.display.sync()

        # Create a loop to monitor the event queue
        while True:
            # Get the next event from the X event queue
            event = self.display.next_event()

            # Check for window state changes (PropertyNotify)
            if event.type == X.PropertyNotify:
                if event.atom == 352:
                    num_of_fs = 0
                    for window in root.query_tree()._data["children"]:
                        self.display.sync()
                        try:
                            width = window.get_geometry()._data["width"]
                            height = window.get_geometry()._data["height"]
                            # Check if the window is mapped and fullscreen
                            if window.get_attributes().map_state != 0:
                                if (
                                    width == screen.width_in_pixels
                                    and height == screen.height_in_pixels
                                ):
                                    num_of_fs += 1
                        except Xlib.error.BadDrawable as e:
                            # Uhhhh
                            # Ig this is a window that was destroyed?
                            # Let's just ignore that
                            pass

                    if num_of_fs > 1:
                        self.fullscreen_active.emit(True)
                    else:
                        self.fullscreen_active.emit(False)

            # Flush the display buffer if needed
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
