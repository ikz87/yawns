import gi
gi.require_version("Gtk", "3.0")  # Ensure compatibility with GTK 3
from gi.repository import Gtk

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
    
    # Lookup the icon
    icon_info = icon_theme.lookup_icon(icon_name, size, Gtk.IconLookupFlags.USE_BUILTIN)
    
    if icon_info:
        return icon_info.get_filename()
    return None
