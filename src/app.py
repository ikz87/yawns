import sys
import configparser
import signal
import os
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtWidgets import QApplication
from dbus_next.constants import MessageType
from yawns_notifications import BaseYawn, YawnType, CornerYawn, CenterYawn
from yawns_manager import NotificationManager
from dbus_next.aio import MessageBus
from dbus_next.message import Message
import asyncio
from Xlib import X
from Xlib.display import Display
from Xlib.Xatom import ATOM
import Xlib
import Xlib.threaded


class FullscreenMonitor(QThread):
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
                    for window in root.query_tree()._data['children']:
                        self.display.sync()
                        try:
                            width = window.get_geometry()._data["width"]
                            height = window.get_geometry()._data["height"]
                            # Check if the window is mapped and fullscreen
                            if window.get_attributes().map_state != 0:
                                if width == screen.width_in_pixels and height == screen.height_in_pixels:
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
        self.manager.activate_notification = self.activate_notification
        self.bus.export('/org/freedesktop/Notifications', self.manager)
        await self.bus.request_name('org.freedesktop.Notifications')
        print("Yawns manager running...")

    def notify_app(self, info_dict: dict):
        """Emit a PyQt signal when a notification is received."""
        filtered_dict = {k:v for k,v in info_dict.items() if k != "pixmap_data"}
        #print(f"Received notification:\n{filtered_dict}")
        self.notification_received.emit(info_dict)

    def close_notification(self, notification, id=None, reason=0):
        message = None
        if notification:
            notification.close()
            id = notification.info_dict["notification_id"]
            sender_id = notification.info_dict["sender_id"]
            message = Message(
                destination=sender_id,
                message_type=MessageType.SIGNAL, # Signal type
                signature="uu",
                interface='org.freedesktop.Notifications',
                path='/org/freedesktop/Notifications',
                member='NotificationClosed',
                body=[int(id), int(reason)]
            )
        else:
            sender_id = "0"
            message = Message(
                destination=sender_id,
                message_type=MessageType.SIGNAL, # Signal type
                signature="uu",
                interface='org.freedesktop.Notifications',
                path='/org/freedesktop/Notifications',
                member='NotificationClosed',
                body=[int(id), int(reason)]
            )
        self.bus.send(message)

    def activate_notification(self, info_dict: dict):
        # This doesn't actually work and I have no idea why
        # TODO: Fix this, I guess :(
        actions = info_dict.get('actions', [])
        if actions and len(actions) > 1:
            action_key = actions[0]
            message = Message(
                destination=info_dict["sender_id"],
                message_type=MessageType.SIGNAL, # Signal type
                signature="us",
                interface='org.freedesktop.Notifications',
                path='/org/freedesktop/Notifications',
                member='ActionInvoked',
                body=[info_dict["notification_id"], action_key]
            )
            self.bus.send(message)
            # ^ I'm just copying what dunst does.
            # Not sure if they do something else behind the scenes
            # but this doesn't work for me
        else:
            print("No actions available to invoke.")
            return

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
    notification_closed = pyqtSignal(BaseYawn)
    notification_activated = pyqtSignal(dict)

    def __init__(self, appname, x11_display):
        self.setAttribute(Qt.AA_X11InitThreads)
        super().__init__(appname)
        self.display = x11_display
        # Use local qss
        self.setStyleSheet(open(PROGRAM_DIR + "/style.qss", "r").read())

        # Arrays for storing yawns
        self.corner_yawns = []
        self.center_yawns = []
        self.fullscreen_detected = False

    def handle_fullscreen_change(self, fullscreen):
        """
        Hide and show yawns depending on urgency and fullscreen state
        """
        global CONFIG
        self.fullscreen_detected = fullscreen
        min_urgency = int(CONFIG["corner"]["fs_urgency"])
        for yawn in self.corner_yawns:
            urgency = int(yawn.info_dict["hints"]["urgency"].value)
            if urgency < min_urgency and fullscreen:
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
        if "yawn_type" in info_dict["hints"]:
            yawn_type = int(info_dict["hints"]["yawn_type"].value)
            if yawn_type == YawnType.CORNER.value:
                print("Showing as a corner yawn")
                self.show_corner_yawn(info_dict)
            elif yawn_type == YawnType.CENTER.value:
                print("Showing as a center yawn")
                self.show_center_yawn(info_dict)
            else:
                print("Sending as fallback yawn")
                fallback(info_dict)
        else:
            print("Sending as fallback yawn")
            fallback(info_dict)

        # Run command after showing the yawn
        if CONFIG["general"]["command"]:
            command = os.path.expanduser(CONFIG["general"]["command"])
            subprocess.call([command,
                             info_dict["app_name"],
                             info_dict["summary"],
                             info_dict["body"],
                             info_dict["app_icon"],
                             str(info_dict["hints"]["urgency"].value),
                             ])

    def show_corner_yawn(self, info_dict):
        # First check the replace id
        if info_dict["replaces_id"] != 0:
            for notification in self.center_yawns:
                if notification.info_dict["replaces_id"] == info_dict["replaces_id"]:
                    notification.info_dict = info_dict
                    notification.close()
            for notification in self.corner_yawns:
                if notification.info_dict["replaces_id"] == info_dict["replaces_id"]:
                    notification.info_dict = info_dict
                    notification.update_content()
                    return
        global CONFIG
        child_window = CornerYawn(self, CONFIG, info_dict)
        min_urgency = int(CONFIG["corner"]["fs_urgency"])
        urgency = int(info_dict["hints"]["urgency"].value)
        if urgency < min_urgency and self.fullscreen_detected:
            pass
        else:
            child_window.show()

    def show_center_yawn(self, info_dict):
        if info_dict["replaces_id"] != 0:
            for notification in self.corner_yawns:
                if notification.info_dict["replaces_id"] == info_dict["replaces_id"]:
                    notification.info_dict = info_dict
                    notification.close()
            for notification in self.center_yawns:
                if notification.info_dict["replaces_id"] == info_dict["replaces_id"]:
                    notification.info_dict = info_dict
                    notification.update_content()
                    return
        global CONFIG
        child_window = CenterYawn(self, CONFIG, info_dict)
        min_urgency = int(CONFIG["center"]["fs_urgency"])
        urgency = int(info_dict["hints"]["urgency"].value)
        if urgency < min_urgency and self.fullscreen_detected:
            pass
        else:
            child_window.show()


def handle_sigint():
    """Handle Ctrl+C to gracefully exit."""
    print("\nCtrl+C pressed. Exiting...")
    manager_thread.stop()
    app.quit()


if __name__ == '__main__':
    # Configuration
    global CONFIG
    global PROGRAM_DIR
    PROGRAM_DIR = os.path.dirname(os.path.abspath(sys.argv[-1]))
    CONFIG = configparser.ConfigParser()
    CONFIG.read('./config.ini')

    # Initialize the application
    x11_display = Display()
    app = YawnsApp(["yawns"], x11_display)
    app.setQuitOnLastWindowClosed(False)

    # Start the NotificationManager in a QThread
    manager_thread = NotificationManagerThread()
    manager_thread.notification_received.connect(app.select_yawn_type)
    app.notification_closed.connect(manager_thread.close_notification)
    app.notification_activated.connect(manager_thread.activate_notification)
    manager_thread.start()

    # Monitor fullscreen changes in a QThread
    fullscreen_monitor_thread = FullscreenMonitor(x11_display)
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

