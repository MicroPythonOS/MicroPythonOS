#!/bin/sh

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

#size=0x200000 # 2MB
#~/sources/mklittlefs/mklittlefs -c "$mydir"/../internal_filesystem/ -s "$size" internal_filesystem.bin

#size=0x520000
#~/sources/mklittlefs/mklittlefs -c "$mydir"/../../../internalsd_zips_removed_gb_romart -s "$size" internalsd_zips_removed_gb_romart.bin

size=0x700000 # 16MB filesystem
# ESP32 doesnt support anything other than -b 4096, unfortunately...
~/sources/mklittlefs/mklittlefs -b 4096 -c "$mydir"/../internal_filesystem/ -s "$size" internal_filesystem.bin
