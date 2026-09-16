#!/usr/bin/env bash
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root. Exiting."
    exit 1
fi
pkgname=yawns
program_dir=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

# Install the main program
install -Dm755 "$program_dir/src/app.py" "/usr/share/$pkgname/app.py"

# Install Python files
install -Dm644 "$program_dir/src/yawns_manager.py" "/usr/share/$pkgname/yawns_manager.py"
install -Dm644 "$program_dir/src/gtk_helpers.py" "/usr/share/$pkgname/gtk_helpers.py"
install -Dm644 "$program_dir/src/backends/X11.py" "/usr/share/$pkgname/backends/X11.py"
install -Dm644 "$program_dir/src/backends/Wayland.py" "/usr/share/$pkgname/backends/Wayland.py"

# Build and install the native Wayland helper (layer-shell support)
native_dir="$program_dir/src/backends/wayland"
if command -v make >/dev/null 2>&1 && pkg-config --exists Qt6WaylandClient; then
    if make -C "$native_dir"; then
        install -Dm755 "$native_dir/build/libyawns_wayland.so" \
            "/usr/lib/$pkgname/backends/wayland/libyawns_wayland.so"
    else
        echo "Warning: could not build the Wayland helper; Wayland support disabled."
    fi
else
    echo "Warning: Qt6 Wayland dev files or make not found; skipping Wayland helper."
fi

# Install yawns_notifications package
install -d "/usr/share/$pkgname/yawns_notifications"
for f in "$program_dir/src/yawns_notifications/"*.py; do
    install -m644 "$f" "/usr/share/$pkgname/yawns_notifications/"
done

# Install assets
install -Dm644 "$program_dir/assets/yawns-logo.png" "/usr/share/$pkgname/assets/yawns-logo.png"
install -Dm644 "$program_dir/assets/vinyl.png" "/usr/share/$pkgname/assets/vinyl.png"

# Install configuration and style files to system-wide config directory
install -Dm644 "$program_dir/src/style.qss" "/usr/share/$pkgname/style.qss"
install -Dm644 "$program_dir/src/config.ini" "/usr/share/$pkgname/config.ini"

# Create a wrapper script for first-run setup and execution
install -Dm755 -d "$pkgdir/usr/bin"  # Ensure the directory exists for the wrapper script
echo '#!/bin/bash
if [ ! -d "$HOME/.config/yawns" ]; then
    mkdir -p "$HOME/.config/yawns"
    cp -r /usr/share/yawns/* "$HOME/.config/yawns"
fi
exec python3 /usr/share/yawns/app.py "$@"' > "/usr/bin/$pkgname"
chmod +x "/usr/bin/$pkgname"

echo "Yawns has been installed. Be sure to also install all the python modules in src/requierements.txt"
