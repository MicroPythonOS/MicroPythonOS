#!/bin/bash

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
codebasedir=$(readlink -f "$mydir"/..) # build process needs absolute paths

target="$1"
buildtype="$2"
subtarget="$3"

if [ -z "$target" -o -z "$buildtype" ]; then
	echo "Usage: $0 target buildtype [optional subtarget]"
	echo "Usage: $0 <esp32 or unix or macOS> <dev or prod> [<waveshare-esp32-s3-touch-lcd-2 or fri3d-2024>]"
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


# This assumes all the git submodules have been checked out recursively

echo "Fetch tags for lib/SDL, otherwise lvgl_micropython's make.py script can't checkout a specific tag..."
pushd "$codebasedir"/lvgl_micropython/lib/SDL
git fetch --unshallow origin 2>/dev/null # will give error if already done
# Or fetch all refs without unshallowing (keeps it shallow but adds refs)
git fetch origin 'refs/tags/*:refs/tags/*'
popd

echo "Check need to add esp32-camera..."
idfile="$codebasedir"/lvgl_micropython/lib/micropython/ports/esp32/main/idf_component.yml
if ! grep esp32-camera "$idfile"; then
	echo "Adding esp32-camera to $idfile"
	echo "  espressif/esp32-camera:
    git: https://github.com/MicroPythonOS/esp32-camera" >> "$idfile"
	echo "Resulting file:"
	cat "$idfile"
else
	echo "No need to add esp32-camera to $idfile"
fi

echo "Check need to add lvgl_micropython manifest to micropython-camera-API's manifest..."
camani="$codebasedir"/micropython-camera-API/src/manifest.py
rellvglmani=lvgl_micropython/build/manifest.py
if ! grep "$rellvglmani" "$idfile"; then
	abslvglmani="$codebasedir"/"$rellvglmani"
	echo "Adding include(\"$abslvglmani\") to $camani"
	echo >> "$camani" # needs newline because file doesn't have newline at the end
	echo "include(\"$abslvglmani\") # workaround to prevent micropython-camera-API from overriding the lvgl_micropython manifest..." >> "$camani"
	echo "Resulting file:"
	cat "$camani"
else
	echo "No need to add include(\"$abslvglmani\") to $camani"
fi

echo "Check need to add asyncio..."
manifile="$codebasedir"/lvgl_micropython/lib/micropython/ports/unix/variants/manifest.py
if ! grep asyncio "$manifile"; then
	echo "Adding asyncio to $manifile"
	echo 'include("$(MPY_DIR)/extmod/asyncio") # needed to have asyncio, which is used by aiohttp, which has used by websockets' >> "$manifile"
	echo "Resulting file:"
	cat "$manifile"
else
	echo "No need to add asyncio to $manifile"
fi

# unix and macOS builds need these symlinks because make.py doesn't handle USER_C_MODULE arguments for them:
echo "Symlinking secp256k1-embedded-ecdh for unix and macOS builds..."
ln -sf ../../secp256k1-embedded-ecdh "$codebasedir"/lvgl_micropython/ext_mod/secp256k1-embedded-ecdh
echo "Symlinking c_mpos for unix and macOS builds..."
ln -sf ../../c_mpos "$codebasedir"/lvgl_micropython/ext_mod/c_mpos

if [ "$buildtype" == "prod" ]; then
	freezefs="$codebasedir"/scripts/freezefs_mount_builtin.sh
	echo "It's a $buildtype build, running $freezefs"
	$freezefs
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
		manifest=$(readlink -f "$codebasedir"/manifests/"$manifest")
		frozenmanifest="FROZEN_MANIFEST=$manifest"
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
	pushd "$codebasedir"/lvgl_micropython/
	python3 make.py --ota --partition-size=4194304 --flash-size=16 esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT DISPLAY=st7789 INDEV=cst816s USER_C_MODULE="$codebasedir"/micropython-camera-API/src/micropython.cmake USER_C_MODULE="$codebasedir"/secp256k1-embedded-ecdh/micropython.cmake USER_C_MODULE="$codebasedir"/c_mpos/micropython.cmake CONFIG_FREERTOS_USE_TRACE_FACILITY=y CONFIG_FREERTOS_VTASKLIST_INCLUDE_COREID=y CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS=y "$frozenmanifest"
	popd
elif [ "$target" == "unix" -o "$target" == "macOS" ]; then
	if [ "$buildtype" == "prod" ]; then
		manifest=$(readlink -f "$codebasedir"/manifests/manifest_unix.py)
		frozenmanifest="FROZEN_MANIFEST=$manifest"
	fi
	# build for desktop
	#python3 make.py "$target"  DISPLAY=sdl_display INDEV=sdl_pointer INDEV=sdl_keyboard "$manifest"
	# LV_CFLAGS are passed to USER_C_MODULES
	# STRIP= makes it so that debug symbols are kept
	pushd "$codebasedir"/lvgl_micropython/
	# USER_C_MODULE doesn't seem to work properly so there are symlinks in lvgl_micropython/extmod/
	python3 make.py "$target" LV_CFLAGS="-g -O0 -ggdb -ljpeg" STRIP=  DISPLAY=sdl_display INDEV=sdl_pointer INDEV=sdl_keyboard "$manifest"
	popd
else
	echo "invalid target $target"
fi

