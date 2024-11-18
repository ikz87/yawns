from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next.aio import MessageBus
from dbus_next import Variant
import asyncio


class NotificationDaemon(ServiceInterface):
    def __init__(self):
        super().__init__('org.freedesktop.Notifications')
        self.notification_id = 1

    @method()
    def GetServerInformation(self) -> 'ssss':
        return ["yawns", "kz87", "alpha", "0.1"]

    @method()
    def GetCapabilities(self) -> 'as':
        return ["body", "actions", "icon-static"]

    @method()
    def Notify(self, app_name: 's', replaces_id: 'u', app_icon: 's', 
               summary: 's', body: 's', actions: 'as', hints: 'a{sv}', 
               expire_timeout: 'i') -> 'u':
        if replaces_id == 0:
            self.notification_id += 1
            notification_id = self.notification_id
        else:
            notification_id = replaces_id
        # Print each method argument formatted
        print(f"Notifying with ID {notification_id}, app_name: {app_name}, replaces_id: {replaces_id}, app_icon: {app_icon}, summary: {summary}, body: {body}, actions: {actions}, hints: {hints}, expire_timeout: {expire_timeout}")
        # Implement notification logic here (e.g., show notification, play sound, etc.)
        # Return the unique notification ID for future reference or updates to the notification
        # Example: Return the same ID as provided in replaces_id if it's non-zero, or generate a new ID if it's zero
        # Ensure to handle the case when the notification ID is not unique and replace any existing notifications with the same ID
        # Returning a single integer as expected in the Notify method
        return notification_id  # Single integer as expected

    @method()
    def CloseNotification(self, id: 'u'):
        print(f"Closing notification with ID {id}. Emitting NotificationClosed signal.")
        self.NotificationClosed(id, 1)  # Example reason code 1

    @signal()
    def NotificationClosed(self, id: 'u', reason: 'u'):
        print(f"NotificationClosed emitted with ID {id}, reason {reason}")
        # No return statement needed for fire-and-forget signal

async def main():
    bus = await MessageBus().connect()
    daemon = NotificationDaemon()
    bus.export('/org/freedesktop/Notifications', daemon)

    await bus.request_name('org.freedesktop.Notifications')
    print("Notification manager running...")
    await asyncio.Future()  # Run forever

if __name__ == '__main__':
    asyncio.run(main())

