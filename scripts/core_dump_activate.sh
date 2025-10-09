# you want this not stripped:
# file ~/projects/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_unix
# ~/projects/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_unix: ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, BuildID[sha1]=f5c2fd31fd06ac76f9ba4eb031b383dfbc3a1b3c, for GNU/Linux 3.2.0, with debug_info, not stripped
# 
# To get that, run it with STRIP= and maybe also that LV_CFLAGS:
# python3 make.py "$target" LV_CFLAGS="-g -O0 -ggdb" STRIP=  DISPLAY=sdl_display INDEV=sdl_pointer INDEV=sdl_keyboard "$manifest"

ulimit -c unlimited
sudo sysctl -w kernel.core_pattern=/tmp/core.%p
