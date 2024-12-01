import time
from cssutils import os
from dbus_next.constants import MessageType
from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next.aio import MessageBus
from dbus_next.message import Message
from gtk_helpers import find_icon
from PIL import Image
import io
import asyncio

from yawns_notifications import BaseYawn


class NotificationManager(ServiceInterface):
    def __init__(self, bus):
        super().__init__("org.freedesktop.Notifications")
        self.notification_id = 0
        self.bus = bus
        self.current_sender = ""

        def handle_message(message: Message):
            """Handle incoming D-Bus messages and log the sender."""
            self.current_sender = message.sender  # Save the sender somewhere

        self.bus.add_message_handler(handle_message)

    @method()
    def GetServerInformation(self) -> "ssss":
        return ["yawns", "kz87", "alpha", "0.1"]

    @method()
    def GetCapabilities(self) -> "as":
        return ["body", "actions", "icon-static"]

    @method()
    def Notify(
        self,
        app_name: "s",
        replaces_id: "u",
        app_icon: "s",
        summary: "s",
        body: "s",
        actions: "as",
        hints: "a{sv}",
        expire_timeout: "i",
    ) -> "u":

        def construct_image(image_data):
            image = Image.frombytes(
                "RGB", 
                (image_data[0], image_data[1]),  # width, height
                bytes(image_data[6]),  # RGB data (ay) part
                "raw", 
                "RGB", 
                image_data[2],  # rowstride
                image_data[3],  # channels (3 or 4)
            )
            if image_data[3]:  # has_alpha
                image = image.convert("RGBA")
            # Save the image as PNG to a BytesIO object
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format="PNG")
            img_byte_arr = img_byte_arr.getvalue()
            return img_byte_arr

        # Load the image according to the freedesktop specification
        # See here: https://specifications.freedesktop.org/notification-spec/1.2/icons-and-images.html#icons-and-images-formats
        img_byte_arr = None
        if "image-data" in hints:
            try:
                img_byte_arr = construct_image(hints["image-data"].value)
            except Exception as e:
                print(f"Error loading image: {e}")

        elif not img_byte_arr and "image-path" in hints:
            image_path = hints["image-path"].value.replace("file://", "")
            if os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as img_file:
                        img_byte_arr = img_file.read()
                except Exception as e:
                    print(f"Error opening image file: {e}")
            else:
                fd_icon = find_icon(image_path)
                if fd_icon:
                    try:
                        with open(image_path, "rb") as img_file:
                            img_byte_arr = img_file.read()
                    except Exception as e:
                        print(f"Error opening image file: {e}")
                else:
                    print(f"Provided image-path is neither a valid image or name in a freedesktop.org-compliant icon theme: {image_path}")

        elif not img_byte_arr and app_icon:
            image_path = app_icon.replace("file://", "")
            if os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as img_file:
                        img_byte_arr = img_file.read()
                except Exception as e:
                    print(f"Error opening image file: {e}")
            else:
                fd_icon = find_icon(image_path)
                if fd_icon:
                    try:
                        with open(image_path, "rb") as img_file:
                            img_byte_arr = img_file.read()
                    except Exception as e:
                        print(f"Error opening image file: {e}")
                else:
                    print(f"Provided app_icon is neither a valid image or name in a freedesktop.org-compliant icon theme: {image_path}")

        elif not img_byte_arr and "icon_data" in hints:
            try:
                img_byte_arr = construct_image(hints["icon_data"].value)
            except Exception as e:
                print(f"Error loading image: {e}")


        self.notification_id += 1
        info_dict = {
            "app_name": app_name,
            "replaces_id": replaces_id,
            "notification_id": self.notification_id,
            "app_icon": app_icon,
            "summary": summary,
            "body": body,
            "actions": actions,
            "hints": hints,
            "expire_timeout": expire_timeout,
            "sender_id": self.current_sender,
            "img_byte_arr": img_byte_arr
        }

        # self.activate_notification(info_dict)
        self.notify_app(info_dict)

        return self.notification_id  # Return the notification ID

    @method()
    def CloseNotification(self, id: "u"):
        # I don't even know if this will get used
        # but in theory the sender should be able to close
        # the notification by accessing this method
        # Edit: I am a fool, this does indeed get used quite a bit
        self.close_notification(id, 3, self.current_sender)

    def notify_app(self, info_dict):
        pass

    def close_notification(self, id, reason, sender_id):
        pass

    def do_action_on_notification(self, id, action, sender_id):
        pass


async def main():
    bus = await MessageBus().connect()
    daemon = NotificationManager(bus)

    # Export the service and request a name
    bus.export("/org/freedesktop/Notifications", daemon)
    await bus.request_name("org.freedesktop.Notifications")

    print("Notification manager running...")
    await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
