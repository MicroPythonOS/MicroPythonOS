#!/bin/bash

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
twoup=$(readlink -f "$mydir"/../..) # build process needs absolute paths
oneup=$(readlink -f "$mydir"/..) # build process needs absolute paths

target="$1"
buildtype="$2"
subtarget="$3"

if [ -z "$target" -o -z "$buildtype" ]; then
	echo "Usage: $0 target buildtype [optional subtarget]"
	echo "Usage: $0 <esp32 or unix or macos> <dev or prod> [<waveshare-esp32-s3-touch-lcd-2 or fri3d-2024>]"
	echo "Example: $0 unix dev"
	echo "Example: $0 esp32 dev fri3d-2024"
	echo "Example: $0 esp32 prod fri3d-2024"
	echo "Example: $0 esp32 dev waveshare-esp32-s3-touch-lcd-2"
	echo "Example: $0 esp32 prod waveshare-esp32-s3-touch-lcd-2"
	echo
	echo "A 'dev' build is without any preinstalled files or builtin/ filsystem, so it will just start with a black screen and you'll have to do: ./scripts/install.sh to install the User Interface."
	echo "A 'prod' build has the files from manifest*.py frozen in. Don't forget to run: ./scripts/freezefs_mount_builtin.sh !"
	exit 1
fi

if [ "$buildtype" == "prod" ]; then
	./scripts/freezefs_mount_builtin.sh
fi



manifest=""
if [ "$target" == "esp32" ]; then
	if [ "$buildtype" == "prod" ]; then
		if [ "$subtarget" == "fri3d-2024" ]; then
			cp internal_filesystem/boot_fri3d-2024.py /tmp/boot.py # dirty hack to have it included as boot.py by the manifest
			manifest="manifest_fri3d-2024.py"
		else
			manifest="manifest.py"
		fi
	else
		echo "Note that you can also prevent the builtin filesystem from being mounted by umounting it and creating a builtin/ folder."
	fi
	# Build for https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-2.
	# See https://github.com/lvgl-micropython/lvgl_micropython
	# --ota: support Over-The-Air updates
	# --partition size: both OTA partitions are 4MB
	# --flash-size: total flash size is 16MB
	# --debug: enable debugging from ESP-IDF but makes copying files to it very slow
	# --dual-core-threads: disabled GIL, run code on both CPUs
	# --task-stack-size={stack size in bytes}
	# CONFIG_* sets ESP-IDF options
	# listing processes on the esp32 still doesn't work because no esp32.vtask_list_threads() or something
	# CONFIG_FREERTOS_USE_TRACE_FACILITY=y
	# CONFIG_FREERTOS_VTASKLIST_INCLUDE_COREID=y
	# CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS=y
	[ ! -z "$manifest" ] && frozenmanifest="FROZEN_MANIFEST="$(readlink -f "$manifest")
	pushd "$twoup"/lvgl_micropython
	python3 make.py --ota --partition-size=4194304 --flash-size=16 esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT DISPLAY=st7789 INDEV=cst816s USER_C_MODULE="$twoup"/micropython-camera-API/src/micropython.cmake USER_C_MODULE="$twoup"/secp256k1-embedded-ecdh/micropython.cmake USER_C_MODULE="$oneup"/c_mpos/micropython.cmake CONFIG_FREERTOS_USE_TRACE_FACILITY=y CONFIG_FREERTOS_VTASKLIST_INCLUDE_COREID=y CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS=y "$frozenmanifest"
	popd
elif [ "$target" == "unix" -o "$target" == "macos" ]; then
	if [ "$buildtype" == "prod" ]; then
		manifest="manifest_unix.py"
	fi
	# build for desktop
	#python3 make.py "$target"  DISPLAY=sdl_display INDEV=sdl_pointer INDEV=sdl_keyboard "$manifest"
	# LV_CFLAGS are passed to USER_C_MODULES
	# STRIP= makes it so that debug symbols are kept
	[ ! -z "$manifest" ] && frozenmanifest="FROZEN_MANIFEST="$(readlink -f "$manifest")
	pushd "$twoup"/lvgl_micropython
	python3 make.py "$target" LV_CFLAGS="-g -O0 -ggdb -ljpeg" STRIP=  DISPLAY=sdl_display INDEV=sdl_pointer INDEV=sdl_keyboard "$manifest"
	popd
else
	echo "invalid target $target"
fi

