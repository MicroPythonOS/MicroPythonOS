#. /home/user/projects/MicroPythonOS/claude/.espressif/python_env/idf5.4_py3.11_env/bin/activate

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

cd "$mydir"

rm -rf build


PATH=/home/user/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin/:$PATH make -f Makefile_esp32 </dev/null

mv mpong.mpy ../../internal_filesystem/mpong_esp32.mpy
