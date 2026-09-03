#!/bin/bash
# Install the apps required by the on-device test suite onto /apps/.
# Builtin apps (howto, settings, file_manager, launcher, appstore, about,
# osupdate) are frozen via freezeFS and need no install.
#
# Usage: ./scripts/install_test_apps.sh [--serial-port /dev/ttyACM0]
# Note: com.micropythonos.doom_launcher provides retrogo_launcher.py used
# by test_retrogo_launcher.py.  Symlinked apps are handled by install.sh.

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

serial_args=()
if [ "$1" = "--serial-port" ]; then
    serial_args=(--serial-port "$2")
fi

apps=(
    com.micropythonos.camera
    com.micropythonos.errortest
    com.micropythonos.errortest_resume
    com.micropythonos.lights_out
    com.micropythonos.memory
    com.micropythonos.musicplayer
    com.micropythonos.imageview
    com.micropythonos.scan_bluetooth
    com.micropythonos.sorter
    com.micropythonos.space_invaders
    com.micropythonos.texteditor
    com.micropythonos.helloworld
    com.micropythonos.doom_launcher
    com_micropythonos_nostr
)

for app in "${apps[@]}"; do
    echo "=== Installing $app ==="
    python3 "$mydir/mpos_controller.py" "${serial_args[@]}" \
        installapp "$mydir/../internal_filesystem/apps/$app" \
        || { echo "FAILED: $app"; exit 1; }
done

echo "All test apps installed."