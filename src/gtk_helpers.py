import gi
gi.require_version("Gtk", "3.0")  # Ensure using GTK 3
from gi.repository import Gtk

def find_icon(icon_name, theme_name="Adwaita", size=48):
    """
    Search for an icon in a freedesktop.org-compliant icon theme.

    Args:
        icon_name (str): Name of the icon to search for.
        theme_name (str): Name of the icon theme (default is Adwaita).
        size (int): Size of the icon in pixels (default is 48).

    Returns:
        str: Full path to the icon image, or None if not found.
    """
    # Initialize the icon theme
    icon_theme = Gtk.IconTheme.get_default()
    # Optionally set a custom theme
    if theme_name:
        icon_theme.set_custom_theme(theme_name)
    # Lookup the icon
    icon_info = icon_theme.lookup_icon(icon_name, size, Gtk.IconLookupFlags.USE_BUILTIN)
    if icon_info:
        return icon_info.get_filename()
    return None
