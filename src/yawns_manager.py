import time
import os
from dbus_next.constants import MessageType
from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next.aio import MessageBus
from dbus_next.message import Message
from gtk_helpers import find_icon, find_desktop_entry_icon, debug
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
        return ["yawns", "kz87", "alpha", "1.2"]

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
            width = image_data[0]
            height = image_data[1]
            rowstride = image_data[2]
            has_alpha = image_data[3]
            bits_per_sample = image_data[4]
            channels = image_data[5]
            data = bytes(image_data[6])

            # Allow RGBA images (used for discord pfps, haven't seen 
            # them elsewhere)
            mode = "RGBA" if has_alpha else "RGB"

            image = Image.frombytes(
                mode,
                (width, height),
                data,
                "raw",
                mode,
                rowstride,
            )

            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format="PNG")
            return img_byte_arr.getvalue()

        # Load the image according to the freedesktop specification
        # See here: https://specifications.freedesktop.org/notification-spec/1.2/icons-and-images.html#icons-and-images-formats
        img_byte_arr = None
        debug(
            f"Notify: app_name={app_name!r} app_icon={app_icon!r} "
            f"hints={sorted(hints.keys())}"
        )
        if "image-data" in hints:
            debug("Using 'image-data' hint")
            try:
                img_byte_arr = construct_image(hints["image-data"].value)
            except Exception as e:
                print(f"Error loading image: {e}")

        elif not img_byte_arr and "image-path" in hints:
            image_path = hints["image-path"].value.replace("file://", "")
            debug(f"Using 'image-path' hint: {image_path!r}")
            if os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as img_file:
                        img_byte_arr = img_file.read()
                except Exception as e:
                    print(f"Error opening image file: {e}")
            else:
                fd_icon = find_icon(image_path)
                if fd_icon:
                    debug(f"Resolved image-path {image_path!r} to {fd_icon!r}")
                    try:
                        with open(fd_icon, "rb") as img_file:
                            img_byte_arr = img_file.read()
                    except Exception as e:
                        print(f"Error opening image file: {e}")
                else:
                    print(
                        f"Provided image-path is neither a valid image or name in a freedesktop.org-compliant icon theme: {image_path}"
                    )

        elif not img_byte_arr and app_icon:
            image_path = app_icon.replace("file://", "")
            debug(f"Using 'app_icon': {image_path!r}")
            if os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as img_file:
                        img_byte_arr = img_file.read()
                except Exception as e:
                    print(f"Error opening image file: {e}")
            else:
                fd_icon = find_icon(image_path)
                if fd_icon:
                    debug(f"Resolved app_icon {image_path!r} to {fd_icon!r}")
                    try:
                        with open(fd_icon, "rb") as img_file:
                            img_byte_arr = img_file.read()
                    except Exception as e:
                        print(f"Error opening image file: {e}")
                else:
                    print(
                        f"Provided app_icon is neither a valid image or name in a freedesktop.org-compliant icon theme: {image_path}"
                    )

        elif not img_byte_arr and "icon_data" in hints:
            debug("Using 'icon_data' hint")
            try:
                img_byte_arr = construct_image(hints["icon_data"].value)
            except Exception as e:
                print(f"Error loading image: {e}")

        # No icon was attached to the notification, fall back to the icon of
        # the app that sent it. We try, in order:
        #   1. the "desktop-entry" hint (most reliable when present)
        #   2. the app name used as a .desktop entry name
        #   3. the app name used directly as an icon theme name
        #   4. the lowercased app name as an icon theme name (GTK lookups are
        #      case-sensitive, e.g. "Spotify" vs the "spotify" icon)
        if not img_byte_arr:
            debug("No icon from the notification itself, trying app fallbacks")

            desktop_entry = hints.get("desktop-entry")
            desktop_entry_name = desktop_entry.value if desktop_entry else None
            debug(f"'desktop-entry' hint: {desktop_entry_name!r}")

            candidates = []
            if desktop_entry_name:
                candidates.append(
                    (
                        f"desktop-entry {desktop_entry_name!r}",
                        lambda: find_desktop_entry_icon(desktop_entry_name),
                    )
                )
            if app_name:
                candidates.append(
                    (
                        f"app_name {app_name!r} as desktop entry",
                        lambda: find_desktop_entry_icon(app_name),
                    )
                )
                candidates.append(
                    (
                        f"app_name {app_name!r} as icon theme",
                        lambda: find_icon(app_name),
                    )
                )
                if app_name.lower() != app_name:
                    candidates.append(
                        (
                            f"lowercase app_name {app_name.lower()!r} as icon theme",
                            lambda: find_icon(app_name.lower()),
                        )
                    )

            icon_path = None
            for label, resolve in candidates:
                icon_path = resolve()
                debug(f"{label} -> {icon_path!r}")
                if icon_path:
                    break

            if icon_path:
                try:
                    with open(icon_path, "rb") as img_file:
                        img_byte_arr = img_file.read()
                except Exception as e:
                    print(f"Error opening icon file: {e}")
            else:
                debug("No icon found for notification")

        debug(f"Final img_byte_arr: {'<{} bytes>'.format(len(img_byte_arr)) if img_byte_arr else None}")

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
            "img_byte_arr": img_byte_arr,
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
