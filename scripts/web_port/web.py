# Copyright (c) 2024 - 2025 Kevin G. Schlosser
#
# Emscripten / WebAssembly build target for lvgl_micropython.
#
# This reuses the unix port machinery (LVGL + SDL display/indev drivers,
# machine_sdl, the frozen manifest, ext_mod user C modules) but compiles it
# with the Emscripten toolchain (emcc/em++/emar) and links against
# Emscripten's bundled SDL2 port (-sUSE_SDL=2) instead of a natively built
# libSDL2.a. The result is a WebAssembly module that renders into an HTML
# <canvas>.
#
# Design notes:
#   * REAL_PORT stays 'unix' so all of the unix patches and machine_sdl/
#     machine_timer additions are reused unchanged.
#   * build_sdl is a no-op: Emscripten supplies SDL2 via its ports system.
#   * The static link flag (-static) is removed; it is meaningless for wasm.
#   * MPOS_WEB=1 is passed to the build so ext_mod/lcd_bus/micropython.mk
#     selects the Emscripten SDL include/link path.
#   * Extra link flags (preload-file, shell-file, ASYNCIFY, output name, ...)
#     are taken from the MPOS_WEB_LINK_FLAGS environment variable so the
#     MicroPythonOS-specific packaging can be supplied by the caller without
#     hard-coding MPOS paths into lvgl_micropython.

import os
import sys
import shutil

from .unix import (
    parse_args as _parse_args,
    build_commands as _build_commands,
    build_manifest as _build_manifest,
    force_clean as _force_clean,
    clean as _clean,
    compile as _compile,
    mpy_cross as _mpy_cross,
)

from . import unix
from . import spawn  # noqa: F401  (kept for parity with other builders)
from . import read_file, write_file


# Reuse every unix port file/patch as-is.
unix.REAL_PORT = 'unix'

# Keep references to the original unix patch helpers so we can reuse the
# SDL-related mutations while removing thread/timer-specific additions.
_orig_update_makefile = unix.update_makefile
_orig_update_main = unix.update_main


# Emscripten toolchain executables. These must be on PATH (source emsdk_env.sh).
EMCC = 'emcc'
EMXX = 'em++'
EMAR = 'emar'
EMRANLIB = 'emranlib'


def parse_args(extra_args, lv_cflags, board):
    return _parse_args(extra_args, lv_cflags, board)


def _web_update_makefile():
    _orig_update_makefile()

    data = read_file(unix.REAL_PORT, unix.MAKEFILE_PATH)

    # Web build: prune unix-native sources that depend on pthread/socket/ffi
    # or force thread-only runtime behavior not available in this target.
    # Also skip shared/libc/* since Emscripten provides its own libc (avoids
    # duplicate symbol errors for printf, etc).
    remove_modules = (
        'mpbthciport.c',
        'mpbtstackport_common.c',
        'mpbtstackport_h4.c',
        'mpbtstackport_usb.c',
        'mpnimbleport.c',
        'modtermios.c',
        'modsocket.c',
        'modffi.c',
        'machine_timer.c',
        'shared/libc',
    )
    filtered = []
    for line in data.splitlines():
        if any(name in line for name in remove_modules):
            continue
        filtered.append(line)

    data = '\n'.join(filtered) + '\n'

    write_file(unix.MAKEFILE_PATH, data)


def _web_update_main():
    _orig_update_main()

    data = read_file(unix.REAL_PORT, unix.MAIN_PATH)
    filtered = []
    for line in data.splitlines():
        if 'machine_timer.h' in line:
            continue
        if 'machine_timer_deinit_all(' in line:
            continue
        filtered.append(line)

    write_file(unix.MAIN_PATH, '\n'.join(filtered) + '\n')


def _web_update_modmachine():
    # No timer type registration in web build.
    pass


# Override unix patch hooks for this target only.
unix.update_makefile = _web_update_makefile
unix.update_main = _web_update_main
unix.update_modmachine = _web_update_modmachine


def build_sdl(_):
    # Emscripten provides SDL2 through its ports system (-sUSE_SDL=2);
    # there is nothing to build here.
    pass


# Replace the unix SDL builder before any compile happens.
unix.build_sdl = build_sdl


def build_commands(target, extra_args, script_dir, lv_cflags, board):
    extra_args = _build_commands(target, extra_args, script_dir, lv_cflags, board)

    # The native static-link flag is meaningless for wasm; drop it.
    static_flag = 'LDFLAGS_EXTRA=-static'
    for cmd in (unix.unix_cmd, unix.clean_cmd, unix.compile_cmd,
                unix.submodules_cmd):
        while static_flag in cmd:
            cmd.remove(static_flag)

    # Caller-supplied Emscripten link flags (preload, shell, asyncify, -o ...).
    link_flags = os.environ.get('MPOS_WEB_LINK_FLAGS', '').strip()

    emscripten_vars = [
        # Prevent unix/Makefile from selecting Darwin-specific link flags
        # (-dead_strip, -map) that wasm-ld rejects.
        'UNAME_S=Linux',
        f'CC={EMCC}',
        f'CXX={EMXX}',
        f'LD={EMCC}',
        f'AR={EMAR}',
        f'RANLIB={EMRANLIB}',
        'LDFLAGS_ARCH=',
        # Disable unix-only modules that pull host headers/libraries.
        'MICROPY_PY_FFI=0',
        'MICROPY_PY_BTREE=0',
        'MICROPY_PY_SOCKET=0',
        'MICROPY_PY_TERMIOS=0',
        'MICROPY_PY_THREAD=0',
        'MICROPY_PY_BLUETOOTH=0',
        # mpy-cross is built separately with the host compiler; only the port
        # objects go through emcc.
        'STRIP=',
        # The unix Makefile defaults CWARN to "-Wall -Werror"; clang under
        # Emscripten promotes many benign warnings to errors, so relax it.
        'CWARN=-Wall',
        # Tell ext_mod/lcd_bus to use the Emscripten SDL2 port.
        'MPOS_WEB=1',
        # Emit a .html shell (also produces .js/.wasm/.data).
        'PROG=micropython.html',
        # SIZE command does not work on .html files; disable it for wasm.
        'SIZE=@echo',
    ]

    sdl_compile_flag = '"CFLAGS_EXTRA=-sUSE_SDL=2 -DMPOS_WEB=1 '            \
                       '-DMICROPY_PY_BTREE=0 -DMICROPY_PY_FFI=0 '          \
                       '-DMICROPY_PY_TERMIOS=0 -DMICROPY_PY_SOCKET=0 '     \
                       '-DMICROPY_PY_THREAD=0 -DMICROPY_PY_THREAD_GIL=0 '  \
                       '-Wno-sign-compare -Wno-unused-function '           \
                       '-Wno-double-promotion '                            \
                       '-Wno-unused-command-line-argument '                \
                       '-Wno-missing-field-initializers"'

    web_ldflags = '-sUSE_SDL=2 -sALLOW_MEMORY_GROWTH=1 '                   \
                  '-sINITIAL_MEMORY=268435456 -sMAXIMUM_MEMORY=2147483648 ' \
                  '-sSTACK_SIZE=8388608 -sSTACK_OVERFLOW_CHECK=2 '        \
                  '-sFORCE_FILESYSTEM=1 -sEXIT_RUNTIME=0 '                \
                  '-sASYNCIFY=1 -sASYNCIFY_STACK_SIZE=32768 '            \
                  '-sASSERTIONS=2 --profiling-funcs '                     \
                  '-Wl,--allow-multiple-definition '
    if link_flags:
        web_ldflags += link_flags

    emscripten_vars.append(f'"LDFLAGS_EXTRA={web_ldflags}"')

    for cmd in (unix.unix_cmd, unix.clean_cmd, unix.compile_cmd,
                unix.submodules_cmd):
        # Strip the unix CFLAGS_EXTRA (it carries native-only warning flags)
        # and replace with the Emscripten-friendly variant.
        for i, part in enumerate(list(cmd)):
            if isinstance(part, str) and part.startswith('"CFLAGS_EXTRA='):
                cmd[i] = sdl_compile_flag
                break
        cmd.extend(emscripten_vars)

    return extra_args


def build_manifest(target, script_dir, lvgl_api, displays, indevs,
                   expanders, imus, frozen_manifest):
    _build_manifest(target, script_dir, lvgl_api, displays, indevs,
                    expanders, imus, frozen_manifest)


def clean():
    _clean()


def force_clean(clean_mpy_cross):
    _force_clean(clean_mpy_cross)


def submodules():
    # SDL submodule is not needed (Emscripten supplies SDL2). Still fetch the
    # micropython submodules the unix port relies on.
    berkeley_db = os.path.abspath('lib/micropython/lib/berkeley-db-1.xx/README')
    if not os.path.exists(berkeley_db):
        return_code, _ = unix.spawn(unix.submodules_cmd)
        if return_code != 0:
            sys.exit(return_code)


def compile(*args):  # NOQA
    try:
        _compile(*args)
    except FileNotFoundError as e:
        # For web target, _compile tries to copy the Unix executable which doesn't exist.
        # Ignore that error; we'll copy the Emscripten artifacts instead.
        if 'micropython' not in str(e) or 'build-standard' not in str(e):
            raise

    # For the web target the real artifacts are the Emscripten outputs. Copy
    # them into build/ so the MPOS web build script can collect them.
    # Keep the original 'micropython.*' names so the JS file finds the correct resources.
    variant = unix.variant or 'standard'
    src_dir = f'lib/micropython/ports/unix/build-{variant}'
    out_dir = 'build'
    for ext in ('html', 'js', 'wasm', 'data', 'wasm.map'):
        src = os.path.join(src_dir, f'micropython.{ext}')
        if os.path.exists(src):
            dst = os.path.join(out_dir, f'micropython.{ext}')
            shutil.copyfile(src, dst)
            print(f'web artifact: {dst}')


def mpy_cross():
    _mpy_cross()
