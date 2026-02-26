#!/bin/sh

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

#size=0x200000 # 2MB
#~/sources/mklittlefs/mklittlefs -c "$mydir"/../internal_filesystem/ -s "$size" internal_filesystem.bin

#size=0x520000
#~/sources/mklittlefs/mklittlefs -c "$mydir"/../../../internalsd_zips_removed_gb_romart -s "$size" internalsd_zips_removed_gb_romart.bin

size=0x520000 # 16MB filesystem
#size=0x460000 # 8MB filesystem
~/sources/mklittlefs/mklittlefs -c "$mydir"/../internal_filesystem/ -s "$size" internal_filesystem.bin
