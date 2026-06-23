#!/bin/bash

scriptdir=$(cd "$(dirname "$0")" && pwd -P)
script="$1"
if [ -f "$script" ]; then
    script="$(cd "$(dirname "$script")" && pwd -P)/$(basename "$script")"
fi

echo "Usage:"
echo "$0 # with no arguments just starts it up normally"
echo "$0 scriptfile.py # doesn't initialize anything, just runs scriptfile.py directly"
echo "$0 appname # starts the app by appname, for example: com.example.helloworld"

#export SDL_WINDOW_FULLSCREEN=true

#export HEAPSIZE=8M # default, same a PSRAM on many ESP32-S3 boards
export HEAPSIZE=16M # on desktop, a bit more is warranted (different C library etc)
#export HEAPSIZE=20M
#export HEAPSIZE=64M # fine for fullscreen 1280x720 slides

os_name=$(uname -s)
if [ "$os_name" = "Darwin" ]; then
    echo "Running on macOS"
    binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_macOS
else
    echo "Running on $os_name"
    binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_unix
fi
binary="$(cd "$(dirname "$binary")" && pwd -P)/$(basename "$binary")"
chmod +x "$binary"

pushd "$scriptdir"/../internal_filesystem/

if [ -f "$script" ]; then
    echo "Running script $script"
    "$binary" -v -i "$script"
else
    CONFIG_FILE="prefs/com.micropythonos.settings/config.json"
    set_autostart_config() {
        local mode="$1"
        local early_value="$2"
        mkdir -p "$(dirname "$CONFIG_FILE")"
        python3 - "$CONFIG_FILE" "$mode" "$early_value" <<'PY'
import json
import os
import sys

path = sys.argv[1]
mode = sys.argv[2]
early_value = sys.argv[3]

config = {}
if os.path.exists(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                config = loaded
    except Exception:
        config = {}

if mode == "set":
    config["auto_start_app_early"] = early_value
elif mode == "clear":
    config.pop("auto_start_app_early", None)

config.pop("auto_start_app", None)

with open(path, "w", encoding="utf-8") as f:
    json.dump(config, f, separators=(",", ":"))
PY
    }

    if [ -n "$script" ]; then
        echo "run_desktop.sh: running app $script"
        set_autostart_config "set" "$script"
    else
        echo "Clearing auto_start_app_early and auto_start_app in config file"
        set_autostart_config "clear" ""
    fi
    "$binary" -X heapsize=$HEAPSIZE -v -i -m main # internal_filesystem/main.py is frozen in and can't be changed after compilation
    # Useful for testing a slow device:
    # cpulimit -l 1 "$binary" -- -X heapsize=$HEAPSIZE -v -i -m main # internal_filesystem/main.py is frozen in and can't be changed after compilation
fi

popd
