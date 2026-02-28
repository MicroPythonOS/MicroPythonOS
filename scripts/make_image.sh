# Experimental quick and dirty script to assemble an ESP32 firmware image based on a partition table, internal_filesystem directory, bootloader, and ESP32 "app" binary
mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
# This needs python and the esptool

python3 lvgl_micropython/lib/esp-idf/components/partition_table/gen_esp32part.py --flash-size 16MB partitions_with_retro-go.csv > partitions_with_retro-go_16mb.bin
#python3 lvgl_micropython/lib/esp-idf/components/partition_table/gen_esp32part.py --flash-size 4MB partitions_4mb.csv > partitions_4mb.bin
#python3 lvgl_micropython/lib/esp-idf/components/partition_table/gen_esp32part.py --flash-size 8MB partitions_8mb.csv > partitions_8mb.bin

if [ $? -ne 0 ]; then
	echo "ERROR: Converting partition csv to bin failed!"
	exit 1
fi

"$mydir"/../scripts/mklittlefs.sh

prboom="~/projects/MicroPythonOS/claude/retro-go/prboom-go/build/prboom-go.bin"
launcher="~/projects/MicroPythonOS/claude/retro-go/launcher/build/launcher.bin"
core="~/projects/MicroPythonOS/claude/retro-go/retro-core/build/retro-core.bin"
#ls -al "$launcher" "$core" "$prboom"


#outdir=lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC-SPIRAM/
#~/.espressif/python_env/*/bin/python -m esptool --chip esp32 merge_bin --fill-flash-size=16MB --output image_esp32.bin 0x1000 "$outdir"/bootloader/bootloader.bin 0x8000 partitions_with_retro-go.bin 0x20000 "$outdir"/micropython.bin 0x820000 "$launcher" 0x930000 "$core" 0xa00000 "$prboom" # 0xae0000 "$mydir"/../internalsd_zips_removed_gb_romart.bin $@

outdir=lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/
rm image_esp32s3.bin
#~/.espressif/python_env/*/bin/python -m esptool --chip esp32s3 merge_bin --fill-flash-size=4MB --output image_esp32s3.bin 0x0 "$outdir"/bootloader/bootloader.bin 0x8000 partitions_for_qemu.bin 0x20000 "$outdir"/micropython.bin # 0x820000 "$launcher" 0x930000 "$core" 0xa00000 "$prboom" # 0xae0000 "$mydir"/../internalsd_zips_removed_gb_romart.bin $@
#~/.espressif/python_env/*/bin/python -m esptool --chip esp32s3 merge_bin --fill-flash-size=8MB --output image_esp32s3.bin 0x0 "$outdir"/bootloader/bootloader.bin 0x8000 partitions_for_qemu.bin 0x20000 "$outdir"/micropython.bin 0x3A0000 "$mydir"/../internal_filesystem.bin $@
~/.espressif/python_env/*/bin/python -m esptool --chip esp32s3 merge_bin --fill-flash-size=16MB --output image_esp32s3.bin 0x0 "$outdir"/bootloader/bootloader.bin 0x8000 partitions_with_retro-go_16mb.bin 0x20000 "$outdir"/micropython.bin 0x820000 "$launcher" 0x930000 "$core" 0xa00000 "$prboom" 0xae0000 "$mydir"/../internal_filesystem.bin $@

# Building an image based on an Arduino IDE build also works, although I only tried arduino-esp32 v2.x and not to v3.x
#outdir=~/.cache/arduino/sketches/4012C161135E5B60169BDFEA7F67E0C6
#sketch=Test_Read_Flash.ino
#outdir=~/.cache/arduino/sketches/DF69B76A41013B091A4C9C10734C1710
#sketch=Test_Download_File.ino
#~/.espressif/python_env/*/bin/python -m esptool --chip esp32s3 merge_bin --fill-flash-size=16MB --output image_esp32s3.bin 0x0 "$outdir"/"$sketch".bootloader.bin 0x8000 "$outdir"/"$sketch".partitions.bin 0x10000 "$outdir"/"$sketch".bin 
