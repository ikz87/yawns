import sys
import configparser
import signal
import os
import subprocess
import fnmatch
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtWidgets import QApplication
from dbus_next.constants import MessageType
from yawns_notifications import BaseYawn, YawnType, CornerYawn, CenterYawn, MediaYawn
from yawns_manager import NotificationManager
from dbus_next.aio import MessageBus
from dbus_next.message import Message
import asyncio
from Xlib import X
from Xlib.display import Display
from Xlib.Xatom import ATOM
import argparse
import Xlib
import Xlib.threaded
from pywayland.client import Display as WDisplay
from pywayland.protocol.wayland import WlRegistry

def detect_compositor():
    display = WDisplay()
    display.connect()
    registry = display.get_registry()

    compositor_name = None

    # Will finish later

    display.disconnect()
    return compositor_name or "Unknown Wayland Compositor."

class X11FullscreenMonitor(QThread):
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


class NotificationManagerThread(QThread):
    notification_received = pyqtSignal(dict)
    notification_closed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.manager = None
        self.bus = None

    async def setup_dbus(self):
        """Set up the D-Bus manager and bind the signal."""
        self.bus = await MessageBus().connect()
        self.manager = NotificationManager(self.bus)
        self.manager.notify_app = self.notify_app
        self.manager.close_notification = self.close_notification
        self.manager.do_action_on_notification = self.do_action_on_notification
        self.bus.export("/org/freedesktop/Notifications", self.manager)
        await self.bus.request_name("org.freedesktop.Notifications")
        print("Yawns manager running...")

    def notify_app(self, info_dict: dict):
        """Emit a PyQt signal when a notification is received."""
        filtered_dict = {k: v for k, v in info_dict.items() if k != "pixmap_data"}
        # print(f"Received notification:\n{filtered_dict}")
        self.notification_received.emit(info_dict)

    def close_notification(self, id, reason, sender_id):
        """
        Sends two signals, one (qt) to the yawns app to close the yawn with
        the id provided and another one (dbus) to the sender app to tell it
        the notification has been closed.
        """
        message = Message(
            destination=sender_id,
            message_type=MessageType.SIGNAL,  # Signal type
            signature="uu",
            interface="org.freedesktop.Notifications",
            path="/org/freedesktop/Notifications",
            member="NotificationClosed",
            body=[int(id), int(reason)],
        )
        self.bus.send(message)
        self.notification_closed.emit(id)

    def do_action_on_notification(self, id, action, sender_id):
        """
        Performs an action on notification
        The handling of the action depends on the sender app
        """
        message = Message(
            destination=sender_id,
            message_type=MessageType.SIGNAL,  # Signal type
            signature="us",
            interface="org.freedesktop.Notifications",
            path="/org/freedesktop/Notifications",
            member="ActionInvoked",
            body=[id, action],
        )
        self.bus.send(message)

    def run(self):
        """Run the D-Bus manager in its own thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.setup_dbus())
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def stop(self):
        """Stop the event loop and thread."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.quit()


class YawnsApp(QApplication):
    request_notification_closing = pyqtSignal(int, int, str)
    request_notification_action = pyqtSignal(int, str, str)

    def __init__(self, appname, x11_display):
        self.setAttribute(Qt.AA_X11InitThreads)
        super().__init__(appname)
        self.display = x11_display
        # Use local qss
        self.stylesheet = open(STYLE_PATH, "r").read()
        self.setStyleSheet(self.stylesheet)

        # Arrays for storing yawns
        self.yawn_arrays = {
            "CornerYawn": [],
            "CenterYawn": [],
            "MediaYawn": [],
        }
        self.fullscreen_detected = False

    def handle_fullscreen_change(self, fullscreen):
        """
        Hide and show yawns depending on urgency and fullscreen state
        """
        global CONFIG
        self.fullscreen_detected = fullscreen
        print(f"{fullscreen = }")
        min_corner_urgency = CONFIG.getint("corner", "min_urgency", fallback=2)
        min_center_urgency = CONFIG.getint("center", "min_urgency", fallback=2)
        min_media_urgency = CONFIG.getint("media", "min_urgency", fallback=2)
        for yawn in self.yawn_arrays["CornerYawn"]:
            if yawn.urgency < min_corner_urgency and fullscreen:
                yawn.hide()
            else:
                yawn.show()
                yawn.update_position()

        for yawn in self.yawn_arrays["CenterYawn"]:
            if yawn.urgency < min_center_urgency and fullscreen:
                yawn.hide()
            else:
                yawn.show()
                yawn.update_position()

        for yawn in self.yawn_arrays["MediaYawn"]:
            if yawn.urgency < min_center_urgency and fullscreen:
                yawn.hide()
            else:
                yawn.show()
                yawn.update_position()

    def select_yawn_type(self, info_dict):
        """
        Select the yawn type based on the yawn_type hint in info dict
        """
        global CONFIG
        fallback = self.show_corner_yawn

        yawn_type = None
        if "yawn_type" in info_dict["hints"]:
            yawn_type = int(info_dict["hints"]["yawn_type"].value)
        # Modify yawn_type according to filters in config
        for yawn_type_value, section in enumerate(["corner", "center", "media"]):
            for section_filter in ["app_name", "summary", "body"]:
                filter_values = CONFIG.get(section, section_filter, fallback=None)
                if not filter_values:
                    continue
                filter_values = filter_values.split()
                for filter_value in filter_values:
                    notif_value = info_dict.get(section_filter, None)
                    if not notif_value:
                        break
                    if fnmatch.fnmatch(notif_value, filter_value):
                        yawn_type = yawn_type_value + 1
                        break
        if yawn_type == YawnType.CORNER.value:
            self.show_corner_yawn(info_dict)
        elif yawn_type == YawnType.CENTER.value:
            self.show_center_yawn(info_dict)
        elif yawn_type == YawnType.MEDIA.value:
            self.show_media_yawn(info_dict)
        else:
            fallback(info_dict)

        # Run command after showing the yawn
        if "general" in CONFIG.sections() and "command" in CONFIG["general"]:
            command = os.path.expanduser(CONFIG["general"]["command"])
            urgency_struct = info_dict["hints"].get("urgency", None)
            urgency = 1
            if urgency_struct:
                urgency = int(urgency_struct.value)
            try:
                subprocess.call(
                    [
                        command,
                        info_dict["app_name"],
                        info_dict["summary"],
                        info_dict["body"],
                        info_dict["app_icon"],
                        str(urgency),
                    ]
                )
            except Exception as e:
                print("Error running command:", command)
                print(e)

    def show_corner_yawn(self, info_dict):
        # First check the replace id
        if info_dict["replaces_id"] != 0:
            for notification in self.yawn_arrays["CenterYawn"]:
                if notification.info_dict["replaces_id"] == info_dict["replaces_id"]:
                    notification.info_dict = info_dict
                    notification.close()
            for notification in self.yawn_arrays["CornerYawn"]:
                if notification.info_dict["replaces_id"] == info_dict["replaces_id"]:
                    notification.info_dict = info_dict
                    notification.update_content()
                    return
        global CONFIG
        yawn = CornerYawn(self, CONFIG, info_dict)
        min_urgency = CONFIG.getint("corner", "min_urgency", fallback=0)
        if yawn.urgency < min_urgency and self.fullscreen_detected:
            pass
        else:
            yawn.show()

    def show_center_yawn(self, info_dict):
        if info_dict["replaces_id"] != 0:
            for notification in self.yawn_arrays["CornerYawn"]:
                if notification.info_dict["replaces_id"] == info_dict["replaces_id"]:
                    notification.info_dict = info_dict
                    notification.close()
            for notification in self.yawn_arrays["CenterYawn"]:
                if notification.info_dict["replaces_id"] == info_dict["replaces_id"]:
                    notification.info_dict = info_dict
                    notification.update_content()
                    return
        global CONFIG
        yawn = CenterYawn(self, CONFIG, info_dict)
        min_urgency = CONFIG.getint("center", "min_urgency", fallback=0)
        if yawn.urgency < min_urgency and self.fullscreen_detected:
            pass
        else:
            yawn.show()

    def show_media_yawn(self, info_dict):
        if self.yawn_arrays["MediaYawn"]:
            notification = self.yawn_arrays["MediaYawn"][0]
            notification.info_dict = info_dict
            notification.update_content()
            return

        global CONFIG
        yawn = MediaYawn(self, CONFIG, info_dict)
        min_urgency = CONFIG.getint("media", "min_urgency", fallback=0)
        if yawn.urgency < min_urgency and self.fullscreen_detected:
            pass
        else:
            yawn.show()

    def close_notification(self, notification_id):
        """
        Close the notification with the given ID
        """
        for key in self.yawn_arrays:
            for notification in self.yawn_arrays[key]:
                if notification.info_dict["notification_id"] == notification_id:
                    notification.close()
                    return


def handle_sigint():
    """Handle Ctrl+C to gracefully exit."""
    print("\nCtrl+C pressed. Exiting...")
    manager_thread.stop()
    app.quit()

def check_notification_service():
    """
    Check if there's already a notification service running
    """
    # Define the actual asynchronous function
    async def async_check():
        # Connect to the session bus
        bus = await MessageBus().connect()

        # Create a message to call the `GetNameOwner` method
        message = Message(
            destination="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus",
            member="GetNameOwner",
            signature="s",
            body=["org.freedesktop.Notifications"]
        )

        # Send the message and get a reply
        reply = await bus.call(message)

        if reply.message_type == MessageType.ERROR:
            # If there's an error, it usually means the name is not owned
            if "org.freedesktop.DBus.Error.NameHasNoOwner" in reply.error_name:
                return False  # Name is not taken
            else:
                print(f"An unexpected error occurred: {reply.error_name}")
                sys.exit(1)  # Exit on unexpected errors
        else:
            return True  # Name is taken

    # Run the asynchronous function synchronously
    return asyncio.run(async_check())


if __name__ == "__main__":
    global CONFIG
    global STYLE_PATH
    global CONFIG_PATH
    global VERSION
    VERSION = "yawns v1.1.0"

    # Check if a notification service is already running
    if check_notification_service():
        print("A notification service is already running. Exiting...")
        sys.exit(1)

    # Check the display server
    server = None
    if "WAYLAND_DISPLAY" in os.environ:
        server = "Wayland"

    elif "DISPLAY" in os.environ:
        try:
            result = subprocess.run(["xdpyinfo"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                server = "Xorg"
        except FileNotFoundError:
            # xdpyinfo is not installed
            pass
    if not server:
        print("Unable to detect the display server (Xorg or Wayland). Exiting...")
        sys.exit(1)

    # We just exit for now
    if server == "Wayland":
        compositor = detect_compositor() # <- unfinished function
        #print(f"Compositor detected {compositor}")
        print("Wayland is not supported yet. Exiting...")
        sys.exit(1)

    # CL Arguments
    argparser = argparse.ArgumentParser(
        prog="yawns",
        description="Your Adaptable Widget Notification System")
    argparser.add_argument("-c", "--config", type=str, default=None, help="Path to the config.ini file")
    argparser.add_argument("-s", "--style", type=str, default=None, help="Path to the style.qss file")
    argparser.add_argument("-v", "--version", action="version", version=VERSION)
    args = argparser.parse_args()

    # Configuration
    CONFIG_DIR = os.path.expanduser("~/.config/yawns")
    if args.config:
        CONFIG_PATH = args.config

        # Check if the configuration exists
        if not os.path.isfile(CONFIG_PATH):
            print(f"Configuration file '{CONFIG_PATH}' does not exist. Exiting...")
            sys.exit(1)
    else:
        CONFIG_PATH = CONFIG_DIR + "/config.ini"
    if args.style:
        STYLE_PATH = args.style
        # Check if the style exists
        if not os.path.isfile(STYLE_PATH):
            print(f"Style file '{STYLE_PATH}' does not exist. Exiting...")
            sys.exit(1)
    else:
        STYLE_PATH = CONFIG_DIR + "/style.qss"

    CONFIG = configparser.ConfigParser()
    CONFIG.read(CONFIG_PATH)

    # Initialize the application
    display = Display()
    app = YawnsApp(["yawns"], display)
    app.setQuitOnLastWindowClosed(False)

    # Start the NotificationManager in a QThread
    manager_thread = NotificationManagerThread()

    # This is cumbersome, but we have to connect signals this way
    # because all notification closing should also be handled by the
    # manager primarily
    manager_thread.notification_received.connect(app.select_yawn_type)

    app.request_notification_closing.connect(manager_thread.close_notification)
    app.request_notification_action.connect(manager_thread.do_action_on_notification)

    manager_thread.notification_closed.connect(app.close_notification)
    manager_thread.start()

    # Monitor fullscreen changes in a QThread
    if server == "Xorg":
        fullscreen_monitor_thread = X11FullscreenMonitor(display)
    else:
        pass
        # Some logic here to handle each wayland compositor differently
    fullscreen_monitor_thread.fullscreen_active.connect(app.handle_fullscreen_change)
    fullscreen_monitor_thread.start()

    # Handle Ctrl+C
    signal.signal(signal.SIGINT, lambda *_: handle_sigint())
    timer = QTimer()
    timer.timeout.connect(lambda: None)  # Allow the event loop to process signals
    timer.start(100)

    # Start the PyQt application
    try:
        sys.exit(app.exec_())
    finally:
        manager_thread.stop()
