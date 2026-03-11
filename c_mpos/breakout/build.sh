#!/bin/bash

find / -iname "activate"

ls -al ~/.espressif/python_env/idf5.4_py3.11_env/bin/
ls -al ~/.espressif/python_env/idf5.4_py3.11_env/
ls -al ~/.espressif/python_env/
ls -al ~/.espressif/
ls -al ~

. ~/.espressif/python_env/idf5.4_py3.11_env/bin/activate

pip install pyelftools ar

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

cd "$mydir"

rm -rf build
rm *.mpy

ls -al ~/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin
ls -al ~/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf
ls -al ~/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119
ls -al ~/.espressif/tools/xtensa-esp-elf
ls -al ~/.espressif/tools
ls -al ~/.espressif
PATH=~/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin:$PATH make </dev/null

mv "$mydir"/breakout*.mpy "$mydir"/../../internal_filesystem/apps/com.micropythonos.breakout/assets/
