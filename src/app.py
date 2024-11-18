import sys
import configparser
import signal
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication
from yawn_notifications import CardNotification
from yawn_manager import NotificationManager
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

    def notify_app(self, notif_dict):
        """Emit a PyQt signal when a notification is received."""
        print(f"Received notification: {notif_dict}")
        self.notification_received.emit(notif_dict)

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
        self.notifications = []

    def show_notification(self, notif_dict):
        """Show a notification when triggered by the D-Bus signal."""
        global CONFIG
        child_window = CardNotification(self.primaryScreen(), CONFIG, notif_dict)
        child_window.show()
        timeout = CONFIG["general"]["timeout"]
        QTimer.singleShot(int(timeout), child_window.close)

        self.notifications.append(child_window)


def handle_sigint():
    """Handle Ctrl+C to gracefully exit."""
    print("\nCtrl+C pressed. Exiting...")
    manager_thread.stop()
    app.quit()


if __name__ == '__main__':
    # Configuration
    global CONFIG
    CONFIG = configparser.ConfigParser()
    CONFIG.read('./config.ini')

    # Initialize the application
    app = YawnsApp(["yawns"])
    app.setQuitOnLastWindowClosed(False)

    # Start the NotificationManager in a QThread
    manager_thread = NotificationManagerThread()
    manager_thread.notification_received.connect(app.show_notification)
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

