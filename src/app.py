import sys
import configparser
import signal
import os
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication
from yawns_notifications import YawnType, CardYawn
from yawns_manager import NotificationManager
from dbus_next.aio import MessageBus
import asyncio


class NotificationManagerThread(QThread):
    notification_received = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.loop = asyncio.new_event_loop()
        self.manager = None

    async def setup_dbus(self):
        """Set up the D-Bus manager and bind the signal."""
        self.manager = NotificationManager()
        self.manager.notify_app = self.notify_app
        bus = await MessageBus().connect()
        bus.export('/org/freedesktop/Notifications', self.manager)
        await bus.request_name('org.freedesktop.Notifications')
        print("Yawns manager running...")

    def notify_app(self, info_dict: dict):
        """Emit a PyQt signal when a notification is received."""
        print(f"Received notification:\n{info_dict}")
        self.notification_received.emit(info_dict)

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
    def __init__(self, appname):
        super().__init__(appname)
        # Use local qss
        self.setStyleSheet(open(PROGRAM_DIR + "/style.qss", "r").read())

        # Arrays for storing yawns
        self.card_yawns = []

    def select_yawn_type(self, info_dict):
        """
        Select the yawn type based on the yawn_type hint in info dict
        """
        fallback = self.show_card_yawn
        if "yawn_type" in info_dict["hints"]:
            yawn_type = int(info_dict["hints"]["yawn_type"].value)
            print(f"Yawn type: {yawn_type}, {YawnType.CENTER}")
            if yawn_type == YawnType.CARD.value:
                print("Showing as a card yawn")
                self.show_card_yawn(info_dict)
            elif yawn_type == YawnType.CENTER.value:
                print("Showing as a center yawn")
            else:
                print("Sending as fallback yawn")
                fallback(info_dict)
        else:
            print("Sending as fallback yawn")
            fallback(info_dict)

    def show_card_yawn(self, info_dict):
        # First check the replace id
        if info_dict["replaces_id"] != 0:
            for notification in self.card_yawns:
                if notification.info_dict["replaces_id"] == info_dict["replaces_id"]:
                    notification.info_dict = info_dict
                    notification.update_content()
                    return
        global CONFIG
        child_window = CardYawn(self, CONFIG, info_dict)
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
    app = YawnsApp(["yawns"])
    app.setQuitOnLastWindowClosed(False)

    # Start the NotificationManager in a QThread
    manager_thread = NotificationManagerThread()
    manager_thread.notification_received.connect(app.select_yawn_type)
    manager_thread.start()

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

