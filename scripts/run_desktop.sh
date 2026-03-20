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

export HEAPSIZE=8M # default, same a PSRAM on many ESP32-S3 boards
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
	CONFIG_FILE="data/com.micropythonos.settings/config.json"
	if [ -n "$script" ]; then
		echo "run_desktop.sh: running app $script"
		if [ -f "$CONFIG_FILE" ]; then
			if grep -q '"auto_start_app"' "$CONFIG_FILE"; then
				echo "Updating auto_start_app field using sed"
				sed -i.backup -e 's/"auto_start_app": ".*"/"auto_start_app": "'$script'"/' "$CONFIG_FILE"
			else
				echo "Adding auto_start_app to config file"
				sed -i.backup -E 's/[[:space:]]*}[[:space:]]*$/,"auto_start_app": "'$script'"}/' "$CONFIG_FILE"
			fi
		else
			mkdir -p "$(dirname "$CONFIG_FILE")"
			echo '{"auto_start_app": "'$script'"}' > "$CONFIG_FILE"
		fi
	else
		if [ -f "$CONFIG_FILE" ]; then
			echo "Removing auto_start_app from config file"
			sed -i.backup -E 's/[[:space:]]*,?[[:space:]]*"auto_start_app"[[:space:]]*:[[:space:]]*"[^"]*"[[:space:]]*//g; s/\{[[:space:]]*,/\{/g; s/,[[:space:]]*\}/\}/g' "$CONFIG_FILE"
		fi
	fi
	"$binary" -X heapsize=$HEAPSIZE -v -i -m main # internal_filesystem/main.py is frozen in and can't be changed at runtime
fi

popd
