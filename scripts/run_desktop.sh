#!/bin/bash -x
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

#export HEAPSIZE=8M # 9MB is not enough for slides, 10MB is okay for 5, 16 for 10, 64 for 100s
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

# Fixed by adding lv.image.cache_drop(None) # This helps a lot!

# Now it works with 10M with infinite slides!

# Now not anymore... let's try increasing it.
#export HEAPSIZE=20M # this is fine for 1024x576
#export HEAPSIZE=15M # fine too

export HEAPSIZE=32M # for 1280x720 images in the image viewer
export HEAPSIZE=128M # for 1280x720 images in the image viewer

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

pushd internal_filesystem/
	if [ -f "$script" ]; then
		"$binary"  -v -i "$script"
	elif [ ! -z "$script" ]; then # it's an app name
		scriptdir="apps/$script"
		if [ ! -d "$scriptdir" ]; then
			scriptdir="builtin/apps/$script"
		fi
		if [ ! -d "$scriptdir" ]; then
			echo "ERROR: no app found by the name '$script'"
			exit 1
		fi
		echo "Running app from $scriptdir"
		"$binary" -X heapsize=$HEAPSIZE  -v -i -c "$(cat boot_unix.py main.py) ; import mpos.apps; mpos.apps.start_app('$scriptdir')"
	else
		"$binary" -X heapsize=$HEAPSIZE -v -i -c "$(cat boot_unix.py main.py)"
	fi
		

popd
