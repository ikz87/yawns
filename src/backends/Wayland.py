"""
Wayland backend for yawns.

Keeps the PyQt6 UI untouched and delegates the parts Wayland does not let a
normal application do to a small native helper (libyawns_wayland.so):

* putting each yawn on a `zwlr_layer_surface_v1` layer surface so it can be
  anchored and always-on-top without an xdg_toplevel move() call;
* moving a yawn by updating its layer-shell margins and committing;
* detecting fullscreen toplevels through
  `zwlr_foreign_toplevel_manager_v1`.

The helper is loaded through ctypes and operates on the `wl_display` that Qt
already owns, so no second Wayland connection or event loop is created.
"""

import os
import shutil
import subprocess
from ctypes import CFUNCTYPE, c_char_p, c_int, c_int32, c_uint32, c_void_p
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QObject, pyqtSignal

# Anchors (zwlr_layer_surface_v1_anchor)
ANCHOR_TOP = 1
ANCHOR_BOTTOM = 2
ANCHOR_LEFT = 4
ANCHOR_RIGHT = 8

# Layers (zwlr_layer_shell_v1_layer)
LAYER_BACKGROUND = 0
LAYER_BOTTOM = 1
LAYER_TOP = 2
LAYER_OVERLAY = 3

# Keyboard interactivity (zwlr_layer_surface_v1_keyboard_interactivity)
KEYBOARD_NONE = 0
KEYBOARD_EXCLUSIVE = 1
KEYBOARD_ON_DEMAND = 2

_LIB_NAME = "libyawns_wayland.so"
_THIS_DIR = Path(__file__).resolve().parent
_NATIVE_DIR = _THIS_DIR / "wayland"

_lib = None

_FS_CALLBACK = CFUNCTYPE(None, c_int)


def _library_candidates():
    override = os.environ.get("YAWNS_WAYLAND_LIB")
    if override:
        yield Path(override)
    yield _NATIVE_DIR / "build" / _LIB_NAME
    yield _NATIVE_DIR / _LIB_NAME
    yield Path("/usr/lib/yawns/backends/wayland") / _LIB_NAME
    yield Path("/usr/share/yawns/backends/wayland") / _LIB_NAME
    yield Path("/usr/lib/yawns") / _LIB_NAME


def _build_library():
    make = shutil.which("make")
    if make is None or not (_NATIVE_DIR / "Makefile").is_file():
        return None
    print("Wayland: building the native helper (libyawns_wayland.so)...")
    try:
        subprocess.check_call([make, "-C", str(_NATIVE_DIR)])
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"Wayland: native helper build failed: {exc}")
        return None
    path = _NATIVE_DIR / "build" / _LIB_NAME
    return path if path.is_file() else None


def _load_library():
    global _lib
    if _lib is not None:
        return _lib

    path = next((candidate for candidate in _library_candidates()
                 if candidate.is_file()), None)
    if path is None:
        path = _build_library()
    if path is None:
        raise RuntimeError(
            "Could not find or build libyawns_wayland.so. Build it with "
            f"`make -C {_NATIVE_DIR}` or set YAWNS_WAYLAND_LIB."
        )

    from ctypes import CDLL

    lib = CDLL(str(path))
    lib.yawns_wayland_init.restype = c_int
    lib.yawns_wayland_has_layer_shell.restype = c_int
    lib.yawns_layer_attach.restype = c_int
    lib.yawns_layer_attach.argtypes = [
        c_void_p, c_uint32, c_uint32, c_int32, c_int32, c_int32, c_int32,
        c_uint32, c_uint32, c_char_p, c_void_p,
    ]
    lib.yawns_layer_set_geometry.restype = c_int
    lib.yawns_layer_set_geometry.argtypes = [
        c_void_p, c_uint32, c_int32, c_int32, c_int32, c_int32, c_int32,
        c_int32,
    ]
    lib.yawns_layer_set_layer.restype = c_int
    lib.yawns_layer_set_layer.argtypes = [c_void_p, c_uint32]
    lib.yawns_layer_set_anchors.restype = c_int
    lib.yawns_layer_set_anchors.argtypes = [c_void_p, c_uint32]
    lib.yawns_layer_set_keyboard_interactivity.restype = c_int
    lib.yawns_layer_set_keyboard_interactivity.argtypes = [c_void_p, c_uint32]
    lib.yawns_layer_set_exclusive_zone.restype = c_int
    lib.yawns_layer_set_exclusive_zone.argtypes = [c_void_p, c_int32]
    lib.yawns_layer_detach.restype = None
    lib.yawns_layer_detach.argtypes = [c_void_p]
    lib.yawns_fs_set_callback.restype = None
    lib.yawns_fs_set_callback.argtypes = [_FS_CALLBACK]
    lib.yawns_fs_start.restype = c_int
    lib.yawns_fs_stop.restype = None

    _lib = lib
    return _lib


def init():
    """
    Bind the layer-shell and foreign-toplevel globals on Qt's wl_display.

    Must be called after the QApplication has been created. Returns True when
    the compositor exposes zwlr_layer_shell_v1.
    """
    lib = _load_library()
    if lib.yawns_wayland_init() != 0:
        print("Wayland: could not initialise the native helper.")
        return False
    if lib.yawns_wayland_has_layer_shell() == 0:
        print(
            "Wayland: the compositor does not expose zwlr_layer_shell_v1. "
            "Yawns needs a wlroots-based compositor (sway, Hyprland, ...)."
        )
        return False
    return True


def window_pointer(widget):
    """Return the raw QWindow* of a widget as an int, creating it if needed."""
    handle = widget.windowHandle()
    if handle is None:
        widget.winId()
        handle = widget.windowHandle()
    if handle is None:
        return None
    return int(sip.unwrapinstance(handle))


def setup_yawn_window(yawn):
    """
    Backend hook called from BaseYawn.__init__: attach a layer surface.
    """
    urgency_struct = yawn.info_dict["hints"].get("urgency", None)
    yawn.urgency = 1
    if urgency_struct:
        yawn.urgency = int(urgency_struct.value)

    pointer = window_pointer(yawn)
    if pointer is None:
        print("Wayland: could not resolve the QWindow for a yawn.")
        return
    yawn._wayland_window_ptr = pointer

    screen = yawn.get_target_screen()
    handle = yawn.windowHandle()
    if handle is not None and screen is not None:
        # Make sure the yawn belongs to the configured output so scaling and
        # the layer surface's wl_output match.
        handle.setScreen(screen)
    screen_pointer = int(sip.unwrapinstance(screen)) if screen is not None else None

    result = _load_library().yawns_layer_attach(
        pointer,
        LAYER_TOP,
        ANCHOR_TOP | ANCHOR_LEFT,
        0, 0, 0, 0,
        0,
        KEYBOARD_NONE,
        b"yawns",
        screen_pointer,
    )
    if result != 0:
        print(f"Wayland: failed to attach a layer surface (error {result}).")


def set_geometry(pointer, anchor, margin_top, margin_right, margin_bottom,
                 margin_left, width, height):
    """Update anchor, margins and size for a yawn, then commit."""
    if pointer is None:
        return
    _load_library().yawns_layer_set_geometry(
        pointer, anchor, margin_top, margin_right, margin_bottom, margin_left,
        width, height,
    )


def set_layer(pointer, layer):
    if pointer is not None:
        _load_library().yawns_layer_set_layer(pointer, layer)


def set_anchors(pointer, anchor):
    if pointer is not None:
        _load_library().yawns_layer_set_anchors(pointer, anchor)


def set_keyboard_interactivity(pointer, mode):
    if pointer is not None:
        _load_library().yawns_layer_set_keyboard_interactivity(pointer, mode)


def set_exclusive_zone(pointer, zone):
    if pointer is not None:
        _load_library().yawns_layer_set_exclusive_zone(pointer, zone)


def detach(pointer):
    if pointer is not None:
        _load_library().yawns_layer_detach(pointer)


class FullscreenMonitor(QObject):
    """
    Reports whether a fullscreen toplevel is currently active.

    The foreign-toplevel protocol is dispatched by Qt's own event loop on the
    main thread, so this class is a plain QObject rather than a QThread.
    """

    fullscreen_active = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._callback = _FS_CALLBACK(self._on_fullscreen_changed)

    def _on_fullscreen_changed(self, value):
        self.fullscreen_active.emit(bool(value))

    def start(self):
        library = _load_library()
        library.yawns_fs_set_callback(self._callback)
        if library.yawns_fs_start() == 0:
            print(
                "Wayland: the compositor does not expose "
                "zwlr_foreign_toplevel_manager_v1; fullscreen detection is "
                "disabled."
            )

    def stop(self):
        if _lib is not None:
            _lib.yawns_fs_stop()
