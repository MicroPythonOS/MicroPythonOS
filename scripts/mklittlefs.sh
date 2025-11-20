#!/bin/sh

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

size=0x200000 # 2MB
~/sources/mklittlefs/mklittlefs -c "$mydir"/../internal_filesystem/ -s "$size" internal_filesystem.bin

