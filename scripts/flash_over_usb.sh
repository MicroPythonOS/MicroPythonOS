fwfile="../lvgl_micropython/build/lvgl_micropy_ESP32_GENERIC_S3-SPIRAM_OCT-16.bin"
ls -al $fwfile
echo "Add --erase-all if needed"
sleep 5
# This needs python and the esptool
~/.espressif/python_env/idf5.2_py3.9_env/bin/python -m esptool --chip esp32s3 --before default_reset --after hard_reset write_flash --flash_mode dio --flash_size 16MB --flash_freq 80m $1 0x0 $fwfile 

