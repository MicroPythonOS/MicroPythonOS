#!/bin/bash

# NOTE: ~/.espressif doesn't exist on MacOS
export PATH=~/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin:$PATH
. ~/.espressif/python_env/idf5.4_py3.11_env/bin/activate

# Even though MacOS installs pyelftools, it still complains about No module named 'elftools'
pip install pyelftools ar

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

cd "$mydir"

# Each architecture gets its own object dir (see the Makefile): sharing one
# left the second architecture linking the first one's objects.
rm -rf build build_x64 build_xtensawin
rm -f *.mpy

make </dev/null

mv "$mydir"/breakout*.mpy "$mydir"/../../internal_filesystem/apps/com.micropythonos.breakout/
