from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next.aio import MessageBus
from dbus_next import Variant
import asyncio
import sys

class NotificationManager(ServiceInterface):
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

        notif_dict = {
            'app_name': app_name,
            'replaces_id': replaces_id,
            'app_icon': app_icon,
            'summary': summary,
            'body': body,
            'actions': actions,
            'hints': hints,
            'expire_timeout': expire_timeout
        }

        self.notify_app(notif_dict)
        # Print the notification details for debugging
        #print(f"Notifying with ID {notification_id}, app_name: {app_name}, replaces_id: {replaces_id}, app_icon: {app_icon}, summary: {summary}, body: {body}, actions: {actions}, hints: {hints}, expire_timeout: {expire_timeout}")

        return notification_id  # Return the notification ID

    @method()
    def CloseNotification(self, id: 'u'):
        print(f"Closing notification with ID {id}. Emitting NotificationClosed signal.")
        self.NotificationClosed(id, 1)  # Example reason code 1

    @signal()
    def NotificationClosed(self, id: 'u', reason: 'u'):
        print(f"NotificationClosed emitted with ID {id}, reason {reason}")
        # No return statement needed for fire-and-forget signal

    def notify_app(self, notif_dict):
        pass

async def main():
    bus = await MessageBus().connect()
    daemon = NotificationManager()
    bus.export('/org/freedesktop/Notifications', daemon)

    await bus.request_name('org.freedesktop.Notifications')
    print("Notification manager running...")
    await asyncio.Future()  # Run forever

if __name__ == '__main__':
    asyncio.run(main())

