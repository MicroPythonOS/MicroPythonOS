newversion="$1"

if [ -z "$newversion" ]; then
	echo "$0 newversion"
	exit 1
fi

pushd ~/projects/MicroPythonOS/updates/
cp ~/projects/MicroPythonOS/lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/micropython.bin releases/Waveshare/ESP32-S3-Touch-LCD-2/Waveshare_ESP32-S3-Touch-LCD-2_$newversion.bin
echo "Now update osupdate.json and push it."
popd




