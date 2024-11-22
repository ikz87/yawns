import time
from dbus_next.constants import MessageType
from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next.aio import MessageBus
from dbus_next.message import Message
import asyncio

class NotificationManager(ServiceInterface):
    def __init__(self, bus):
        super().__init__('org.freedesktop.Notifications')
        self.notification_id = 1
        self.bus = bus
        self.current_sender = None

        def handle_message(message: Message):
            """Handle incoming D-Bus messages and log the sender."""
            self.current_sender = message.sender # Save the sender somewhere

        self.bus.add_message_handler(handle_message)

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

        # Load the image asap because it gets deleted instantly 
        image_path = ""
        app_icon_path = ""
        if "image_path" in hints:
            image_path = hints["image_path"].value.replace("file://", "")
        if app_icon:
            app_icon_path = app_icon.replace("file://", "")
        pixmap_data = None
        if image_path:
            with open(image_path, 'rb') as img_file:
                pixmap_data = img_file.read()
        elif app_icon_path:
            with open(app_icon_path, 'rb') as img_file:
                pixmap_data = img_file.read()

        if replaces_id == 0:
            self.notification_id += 1
            notification_id = self.notification_id
        else:
            notification_id = replaces_id

        notif_dict = {
            'app_name': app_name,
            'replaces_id': replaces_id,
            'notification_id': notification_id,
            'app_icon': app_icon,
            'pixmap_data': pixmap_data,
            'summary': summary,
            'body': body,
            'actions': actions,
            'hints': hints,
            'expire_timeout': expire_timeout,
            'sender_id': self.current_sender
        }
        self.notification_id += 1

        #self.activate_notification(notif_dict)
        self.notify_app(notif_dict)

        return replaces_id  # Return the notification ID

    @method()
    def CloseNotification(self, id: 'u'):
        self.NotificationClosed(id, 2)

    @signal()
    def NotificationClosed(self, id: 'u', reason: 'u'):
        pass

    def activate_notification(self, notif_dict):
        # This doesn't actually work and I have no idea why
        # TODO: Fix this, I guess :(
        actions = notif_dict.get('actions', [])
        if actions and len(actions) > 1:
            action_key = actions[0]
            message = Message(
                destination=notif_dict["sender_id"],
                message_type=MessageType.SIGNAL, # Signal type
                signature="us",
                interface='org.freedesktop.Notifications',
                path='/org/freedesktop/Notifications',
                member='ActionInvoked',
                body=[notif_dict["notification_id"], action_key]
            )
            self.bus.send(message)
            message = Message(
                destination=notif_dict["sender_id"],
                message_type=MessageType.SIGNAL, # Signal type
                signature="uu",
                interface='org.freedesktop.Notifications',
                path='/org/freedesktop/Notifications',
                member='NotificationClosed',
                body=[notif_dict["notification_id"], 2]
            )
            self.bus.send(message)
            # ^ I'm just copying what dunst does.
            # Not sure if they do something else behind the scenes
            # but this doesn't work for me
        else:
            print("No actions available to invoke.")
            return

    def notify_app(self, notif_dict):
        pass


async def main():
    bus = await MessageBus().connect()
    daemon = NotificationManager(bus)

    # Export the service and request a name
    bus.export('/org/freedesktop/Notifications', daemon)
    await bus.request_name('org.freedesktop.Notifications')

    print("Notification manager running...")
    await asyncio.Future()  # Run forever

if __name__ == '__main__':
    asyncio.run(main())

