import configparser
import os

import gi
gi.require_version("Gtk", "3.0")  # Ensure compatibility with GTK 3
from gi.repository import Gtk

# Set YAWNS_DEBUG=1 (or true/yes/on) in the environment to get verbose
# logs about how icons are being resolved.
DEBUG = os.environ.get("YAWNS_DEBUG", "").lower() in ("1", "true", "yes", "on")


def debug(*args):
    if DEBUG:
        print("[yawns:icons]", *args, flush=True)


def find_icon(icon_name, size=64):
    """
    Search for an application icon in a freedesktop.org-compliant icon theme.

    Args:
        icon_name (str): Name of the application icon to search for.
        size (int): Size of the icon in pixels (default is 48).

    Returns:
        str: Full path to the icon image, or None if not found.
    """
    # Load the default system icon theme
    icon_theme = Gtk.IconTheme.get_default()
    debug(f"find_icon({icon_name!r}, size={size})")

    # Lookup the icon
    icon_info = icon_theme.lookup_icon(icon_name, size, Gtk.IconLookupFlags.USE_BUILTIN)

    if icon_info:
        path = icon_info.get_filename()
        debug(f"find_icon({icon_name!r}) -> {path!r}")
        return path
    debug(f"find_icon({icon_name!r}) -> not found")
    return None


def _data_dirs():
    """Return the freedesktop.org data directories in lookup order."""
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser(
        "~/.local/share"
    )
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [data_home] + [d for d in data_dirs.split(":") if d]


def _find_desktop_file(desktop_entry):
    """
    Locate a .desktop file by its entry name (with or without the .desktop
    suffix) in the freedesktop.org data directories.
    """
    name = desktop_entry
    if name.endswith(".desktop"):
        name = name[: -len(".desktop")]

    candidates = [name]
    if name.lower() != name:
        candidates.append(name.lower())

    debug(f"_find_desktop_file({desktop_entry!r}): candidates={candidates}, "
          f"data_dirs={_data_dirs()}")

    for base in _data_dirs():
        for candidate in candidates:
            path = os.path.join(base, "applications", candidate + ".desktop")
            if os.path.isfile(path):
                debug(f"_find_desktop_file({desktop_entry!r}) -> {path!r}")
                return path
    debug(f"_find_desktop_file({desktop_entry!r}) -> no .desktop file found")
    return None


def find_desktop_entry_icon(desktop_entry, size=64):
    """
    Resolve the icon associated with a freedesktop.org .desktop entry.

    Args:
        desktop_entry (str): Name of the .desktop entry (the value usually
            found in the notification "desktop-entry" hint).
        size (int): Size of the icon in pixels (default is 64).

    Returns:
        str: Full path to the icon image, or None if not found.
    """
    if not desktop_entry:
        debug("find_desktop_entry_icon: empty desktop-entry, skipping")
        return None

    desktop_file = _find_desktop_file(desktop_entry)
    if not desktop_file:
        return None

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(desktop_file, encoding="utf-8")
        icon = parser.get("Desktop Entry", "Icon", fallback=None)
    except Exception as e:
        print(f"Error parsing desktop entry {desktop_file}: {e}")
        return None

    debug(f"find_desktop_entry_icon({desktop_entry!r}): "
          f"{desktop_file!r} has Icon={icon!r}")

    if not icon:
        return None

    if os.path.isabs(icon):
        resolved = icon if os.path.isfile(icon) else None
        debug(f"find_desktop_entry_icon({desktop_entry!r}) -> {resolved!r}")
        return resolved

    return find_icon(icon, size)
