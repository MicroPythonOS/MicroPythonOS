#!/bin/bash

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
codebasedir=$(readlink -f "$mydir"/..) # build process needs absolute paths

target="$1"
buildtype="$2"
subtarget="$3"

if [ -z "$target" ]; then
	echo "Usage: $0 target"
	echo "Usage: $0 <esp32 or unix or macOS>"
	echo "Example: $0 unix"
	echo "Example: $0 macOS"
	echo "Example: $0 esp32"
	exit 1
fi


# This assumes all the git submodules have been checked out recursively

echo "Fetch tags for lib/SDL, otherwise lvgl_micropython's make.py script can't checkout a specific tag..."
pushd "$codebasedir"/lvgl_micropython/lib/SDL
git fetch --unshallow origin 2>/dev/null # will give error if already done
# Or fetch all refs without unshallowing (keeps it shallow but adds refs)
git fetch origin 'refs/tags/*:refs/tags/*'
popd

idfile="$codebasedir"/lvgl_micropython/lib/micropython/ports/esp32/main/idf_component.yml
echo "Patching $idfile"...

echo "Check need to add esp32-camera..."
if ! grep esp32-camera "$idfile"; then
	echo "Adding esp32-camera to $idfile"
	echo "  mpos/esp32-camera:
    git: https://github.com/MicroPythonOS/esp32-camera" >> "$idfile"
else
	echo "No need to add esp32-camera to $idfile"
fi
echo "Resulting file:"
cat "$idfile"

# Adding it doesn't hurt - it won't be used anyway as RLOTTIE is disabled in lv_conf.h
echo "Check need to add esp_rlottie"
#if ! grep rlottie "$idfile"; then
if false; then
	echo "Adding esp_rlottie to $idfile"
	echo "  esp_rlottie:
    git: https://github.com/MicroPythonOS/esp_rlottie" >> "$idfile"
	echo "Resulting file:"
	cat "$idfile"
else
	echo "No need to add esp_rlottie to $idfile"
fi

echo "Check need to add lvgl_micropython manifest to micropython-camera-API's manifest..."
camani="$codebasedir"/micropython-camera-API/src/manifest.py
rellvglmani=lvgl_micropython/build/manifest.py
abslvglmani="$codebasedir"/"$rellvglmani"
if ! grep "$rellvglmani" "$camani"; then
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
# Only for MicroPython 1.26.1 workaround:
#echo "Applying lvgl_micropython i2c patch..."
#patch -p0 --forward < "$codebasedir"/patches/i2c_ng.patch

echo "Refreshing freezefs..."
"$codebasedir"/scripts/freezefs_mount_builtin.sh

manifest=""
if [ "$target" == "esp32" ]; then
	manifest=$(readlink -f "$codebasedir"/manifests/manifest.py)
	frozenmanifest="FROZEN_MANIFEST=$manifest"
	echo "Note that you can also prevent the builtin filesystem from being mounted by umounting it and creating a builtin/ folder."
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
	rm -rf lib/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/
	python3 make.py --ota --partition-size=4194304 --flash-size=16 esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT DISPLAY=st7789 INDEV=gt911 USER_C_MODULE="$codebasedir"/micropython-camera-API/src/micropython.cmake USER_C_MODULE="$codebasedir"/secp256k1-embedded-ecdh/micropython.cmake USER_C_MODULE="$codebasedir"/c_mpos/micropython.cmake CONFIG_FREERTOS_USE_TRACE_FACILITY=y CONFIG_FREERTOS_VTASKLIST_INCLUDE_COREID=y CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS=y "$frozenmanifest"
	popd
	echo "Grepping..."
	pwd
	grep FrameSize.R480X480 -nril .
elif [ "$target" == "unix" -o "$target" == "macOS" ]; then
	manifest=$(readlink -f "$codebasedir"/manifests/manifest.py)
	frozenmanifest="FROZEN_MANIFEST=$manifest"

	# Comment out @micropython.viper decorator for Unix/macOS builds
	# (cross-compiler doesn't support Viper native code emitter)
	echo "Temporarily commenting out @micropython.viper decorator for Unix/macOS build..."
	stream_wav_file="$codebasedir"/internal_filesystem/lib/mpos/audio/stream_wav.py
	sed -i.backup 's/^@micropython\.viper$/#@micropython.viper/' "$stream_wav_file"

	#if [ "$target" == "unix" ]; then
	if false; then
		# only on unix, because on macos, homebrew install rlottie fails so the compilation runs into: fatal error: 'rlottie_capi.h' file not found on macos"
		# and on esp32, rlottie_create_from_raw() crashes the system
		sed -i.backup 's/#define MICROPY_RLOTTIE 0/#define MICROPY_RLOTTIE 1/' "$codebasedir"/lvgl_micropython/lib/lv_conf.h
		echo "After enabling MICROPY_RLOTTIE:"
		cat "$codebasedir"/lvgl_micropython/lib/lv_conf.h
	fi

	# If it's still running, kill it, otherwise "text file busy"
	pkill -9 -f /lvgl_micropy_unix
	# LV_CFLAGS are passed to USER_C_MODULES (compiler flags only, no linker flags)
	# STRIP= makes it so that debug symbols are kept
	pushd "$codebasedir"/lvgl_micropython/
	# USER_C_MODULE doesn't seem to work properly so there are symlinks in lvgl_micropython/extmod/
	python3 make.py "$target" LV_CFLAGS="-g -O0 -ggdb" STRIP=  DISPLAY=sdl_display INDEV=sdl_pointer INDEV=sdl_keyboard "$frozenmanifest"
	popd

	# Restore RLOTTIE:
	if [ "$target" == "unix" ]; then
		sed -i.backup 's/#define MICROPY_RLOTTIE 1/#define MICROPY_RLOTTIE 0/' "$codebasedir"/lvgl_micropython/lib/lv_conf.h
		#echo "After disabling MICROPY_RLOTTIE:"
		#cat "$codebasedir"/lvgl_micropython/lib/lv_conf.h
	fi

	# Restore @micropython.viper decorator after build
	echo "Restoring @micropython.viper decorator..."
	sed -i.backup 's/^#@micropython\.viper$/@micropython.viper/' "$stream_wav_file"
else
	echo "invalid target $target"
fi

