#!/bin/bash 
scriptdir=$(readlink -f "$0")
scriptdir=$(dirname "$scriptdir")
script="$1"
if [ -f "$script" ]; then
	script=$(readlink -f "$script")
fi

echo "Usage:"
echo "$0 # with no arguments just starts it up normally"
echo "$0 scriptfile.py # doesn't initialize anything, just runs scriptfile.py directly"
echo "$0 appname # starts the app by appname, for example: com.example.helloworld"

#export SDL_WINDOW_FULLSCREEN=true

export HEAPSIZE=8M # default, same a PSRAM on many ESP32-S3 boards
#export HEAPSIZE=9M # 9MB is not enough for slides, 10MB is okay for 5, 16 for 10, 64 for 100s
#export HEAPSIZE=10M # 9MB is not enough for slides, 10MB is okay for 5, 16 for 10, 64 for 100s
#export HEAPSIZE=11M # 9MB is not enough for slides, 10MB is okay for 5, 16 for 10, 64 for 100s
#export HEAPSIZE=12M # 9MB is not enough for slides, 10MB is okay for 5, 16 for 10, 64 for 100s
#export HEAPSIZE=13M # 9MB is not enough for slides, 10MB is okay for 5, 16 for 10, 64 for 100s
#export HEAPSIZE=14M # 9MB is not enough for slides, 10MB is okay for 5, 16 for 10, 64 for 100s
#export HEAPSIZE=15M # 9MB is not enough for slides, 10MB is okay for 5, 15 ok for all

# 15 works infinite with 8 images
# 12 seems to work fine with all images now, doing only gc.collect()
# 10-11 works infinite with 7 images but as soon as I add the next one (big PNG slide 2) it hangs memory alloc

# Makes semse because the error is:
# MemoryError: memory allocation failed, allocating 2518043 bytes
# So every new slide needs 2.5MB extra RAM!
# A 1280x720 slide seems to allocate 5530721 bytes, so 6 bytes per pixel... a bit much but okay...

# Fixed by adding lv.image.cache_drop(None) # This helps a lot!

#export HEAPSIZE=16M # 8-10MB is not enough for 1280x720 slides, 16MB seems enough in windowed mode

#export HEAPSIZE=64M # fine for fullscreen 1280x720 slides


# print os and set binary
os_name=$(uname -s)
if [ "$os_name" = "Darwin" ]; then
	echo "Running on macOS"
	binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_macOS
else
	# other cases can be added here
	echo "Running on $os_name"
	binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_unix
fi

binary=$(readlink -f "$binary")
chmod +x "$binary"

pushd "$scriptdir"/../internal_filesystem/

if [ -f "$script" ]; then
	echo "Running script $script"
	"$binary"  -v -i "$script"
else
	echo "Running app $script"
	CONFIG_FILE="data/com.micropythonos.settings/config.json"
	# Check if config.json exists
	if [ -f "$CONFIG_FILE" ]; then
		# Update the auto_start_app field using sed
		sed -i '' -e 's/"auto_start_app": ".*"/"auto_start_app": "'$script'"/' "$CONFIG_FILE"
	else
		# If config.json doesn't exist, create it with auto_start_app
		echo '{"auto_start_app": "'$script'"}' > "$CONFIG_FILE"
	fi
	"$binary" -X heapsize=$HEAPSIZE  -v -i -c "$(cat main.py)"
fi

popd
