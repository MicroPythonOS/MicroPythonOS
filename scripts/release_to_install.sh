newversion="$1"

if [ -z "$newversion" ]; then
	echo "$0 newversion"
	exit 1
fi

cd ~/projects/MicroPythonOS/install
cp ~/projects/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin firmware_images/Waveshare/ESP32-S3-Touch-LCD-2/Waveshare_ESP32-S3-Touch-LCD-2_$newversion.bin
echo "Now update manifests/Waveshare/ESP32-S3-Touch-LCD-2/Waveshare_ESP32-S3-Touch-LCD-2.json and push it."




