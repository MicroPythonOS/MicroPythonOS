builddir=../lvgl_micropython/build
outdir=../build_outputs/
updatesdir=../updates/

buildfile="$builddir"/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin
updatefile=../lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/micropython.bin

version=$(grep CURRENT_OS_VERSION internal_filesystem/lib/mpos/info.py  | cut -d "=" -f 2 | tr -d " " | tr -d '"')

overwrite="$1"
if [ "$overwrite" != "--overwrite" ] && ls "$outdir"/*"$version"* 2>/dev/null; then
	echo "WARNING: $version already exists, use --overwrite to overwrite it"
	exit 1
fi

./scripts/build_lvgl_micropython.sh esp32 prod fri3d-2024
result=$?
if [ $result -ne 0 ]; then
	echo "build_lvgl_micropython.sh esp32 prod fri3d-2024 got error: $result"
	exit 1
fi
cp "$buildfile" "$outdir"/MicroPythonOS_fri3d-2024_prod_"$version".bin
cp "$updatefile" "$updatesdir"/MicroPythonOS_fri3d-2024_prod_"$version".ota

./scripts/build_lvgl_micropython.sh esp32 dev fri3d-2024
result=$?
if [ $result -ne 0 ]; then
	echo "build_lvgl_micropython.sh esp32 dev fri3d-2024 got error: $result"
	exit 1
fi
cp "$buildfile" "$outdir"/MicroPythonOS_fri3d-2024_dev_"$version".bin

./scripts/build_lvgl_micropython.sh esp32 prod waveshare-esp32-s3-touch-lcd-2
result=$?
if [ $result -ne 0 ]; then
	echo "build_lvgl_micropython.sh esp32 prod waveshare-esp32-s3-touch-lcd-2 got error: $result"
	exit 1
fi
cp "$buildfile" "$outdir"/MicroPythonOS_waveshare-esp32-s3-touch-lcd-2_prod_"$version".bin
cp "$updatefile" "$updatesdir"/MicroPythonOS_waveshare-esp32-s3-touch-lcd-2_prod_"$version".ota

./scripts/build_lvgl_micropython.sh esp32 dev waveshare-esp32-s3-touch-lcd-2
result=$?
if [ $result -ne 0 ]; then
	echo "build_lvgl_micropython.sh esp32 dev waveshare-esp32-s3-touch-lcd-2 got error: $result"
	exit 1
fi
cp "$buildfile" "$outdir"/MicroPythonOS_waveshare-esp32-s3-touch-lcd-2_dev_"$version".bin

./scripts/build_lvgl_micropython.sh unix dev
cp "$builddir"/lvgl_micropy_unix "$outdir"/MicroPythonOS_amd64_linux_"$version".elf
result=$?
if [ $result -ne 0 ]; then
	echo "build_lvgl_micropython.sh esp32 unix dev got error: $result"
	exit 1
fi
