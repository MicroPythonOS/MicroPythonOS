builddir=../lvgl_micropython/build
outdir=../build_outputs

buildfile="$builddir"/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin

./scripts/build_lvgl_micropython.sh esp32 dev fri3d-2024
cp "$buildfile" "$outdir"/MicroPythonOS_fri3d-2024_dev

./scripts/build_lvgl_micropython.sh esp32 prod fri3d-2024
cp "$buildfile" "$outdir"/MicroPythonOS_fri3d-2024_prod

./scripts/build_lvgl_micropython.sh unix dev
cp "$builddir"/lvgl_micropy_unix "$outdir"/MicroPythonOS_amd64_Linux

./scripts/build_lvgl_micropython.sh esp32 prod waveshare-esp32-s3-touch-lcd-2
cp "$buildfile" "$outdir"/MicroPythonOS_waveshare-esp32-s3-touch-lcd-2_prod

./scripts/build_lvgl_micropython.sh esp32 dev waveshare-esp32-s3-touch-lcd-2
cp "$buildfile" "$outdir"/MicroPythonOS_waveshare-esp32-s3-touch-lcd-2_dev

