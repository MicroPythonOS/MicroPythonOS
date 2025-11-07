# you want this not stripped:
# file lvgl_micropython/build/lvgl_micropy_unix
# ~/lvgl_micropython/build/lvgl_micropy_unix: ELF 64-bit LSB pie executable, x86-64, version 1 (SYSV), dynamically linked, interpreter /lib64/ld-linux-x86-64.so.2, BuildID[sha1]=f5c2fd31fd06ac76f9ba4eb031b383dfbc3a1b3c, for GNU/Linux 3.2.0, with debug_info, not stripped
# 
# To get that, compile it with STRIP= and maybe also that LV_CFLAGS - build_mpos.sh will do this by default already:
# python3 make.py "$target" LV_CFLAGS="-g -O0 -ggdb" STRIP=  DISPLAY=sdl_display INDEV=sdl_pointer INDEV=sdl_keyboard "$manifest"

ulimit -c unlimited
sudo sysctl -w kernel.core_pattern=/tmp/core.%p

# Now run it as usual (with run_desktop.sh)
# And when it crashes, the core will be dumped in /tmp/core.XXXXX

# Then analyse it with:
# gdb lvgl_micropython/build/lvgl_micropy_unix /tmp/core.185491

# For example, to see the stack trace of the error:
# (gdb) info stack
