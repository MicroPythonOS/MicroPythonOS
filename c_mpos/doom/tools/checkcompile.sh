#!/bin/bash
# Compile every generated engine file and collect errors (no linking).
cd "$(dirname "$0")/.." || exit 1
mkdir -p tmpcheck
CFLAGS="-std=c99 -Os -Wall -Wno-error -I. -Idoomgeneric -I../../lvgl_micropython/lib/micropython \
  -DCMAP256 -DNORMALUNIX -DLINUX -D_DEFAULT_SOURCE -Wno-unused-but-set-variable \
  -Wno-sign-compare -Wno-missing-braces -Wno-pointer-sign -Wno-format"
fail=0
# Skip platform implementations we do not build (and that need SDL/Allegro).
for f in gen/*.c; do
    case "$(basename "$f")" in
        doomgeneric_allegro.c|doomgeneric_emscripten.c|doomgeneric_linuxvt.c) continue ;;
        doomgeneric_sdl.c|doomgeneric_soso.c|doomgeneric_sosox.c|doomgeneric_win.c) continue ;;
        doomgeneric_xlib.c|i_allegromusic.c|i_allegrosound.c|i_sdlmusic.c|i_sdlsound.c) continue ;;
    esac
    if ! gcc $CFLAGS -c "$f" -o "tmpcheck/$(basename "$f" .c).o" 2> "tmpcheck/$(basename "$f" .c).err"; then
        fail=$((fail+1))
        echo "=== $f"
        grep -E "error:" "tmpcheck/$(basename "$f" .c).err" | head -5
    fi
done
echo "FAILED FILES: $fail"
