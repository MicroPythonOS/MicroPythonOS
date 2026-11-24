# Duke Nukem 3D as a MicroPythonOS core

The app `com.micropythonos.duke3d` runs the DukeNano3D port of Chocolate Duke3D
(the retro-go flavour) as a **flash-resident core**: the same `mpos_core` ABI
that Doom uses (`c_mpos/core_abi.h`), so a 500 KB engine executes from flash
through the instruction cache instead of having to fit in IRAM.

## Layout

```
engine/        DukeNano3D's Game/, Engine/ and SDL/ sources (unchanged except
               where noted). The platform code that talked to retro-go lives
               in core/ instead.
audiolib/      the headers the engine includes (fx_man.h, music.h, ...).
core/          the port:
  duke_core.c      entry table, .data copy, init/tick/stop, fatal-error jump
  duke_platform.c  the retro-go names the engine still uses, on the ABI
  duke_libc.c      heap + read-only stdio + strings/parsing (no libm; the
                   engine is fixed point)
  sdl_video.c      the 320x200 palette surface and the RGB565 band present
  sdl_event.c      ABI key queue -> SDL events
  sdl_system.c     clock/delay/error/mutex shims
  sdl_input.c      "no joysticks"
  duke_audio.c     link-time FX_/MUSIC_ stubs (sound is off; see below)
  lodepng.c/.h     the compacted GRP stores 900+ tiles as PNG
  duke_core.ld     fixed-address link script
build_duke_core.sh builds build_core/esp32s3.xip
```

## Engine seams

The engine is the DukeNano3D source, with a small set of host seams:

* `Game/game.c`: `main()` returns after the start-up (where its own loop would
  begin) and the body of that loop is `duke_run_frame()`, which the host calls
  once per display frame. The engine's menu, level transitions and game tics
  are untouched. `load_duke3d_groupfile()` asks the host for `duke3d.grp`
  directly; the file is the activity's in-RAM GRP, served through `read_file()`.
  The default warp is E1L1 (volume 0, level 0 - the engine's own numbering).
* `Game/global.c` / `Game/game.c`: `Error()` and `gameexit()` record the exit
  and jump out instead of deleting a FreeRTOS task. There is no process to end,
  and returning into the engine after `ShutDown()` would run on freed memory.
* `Game/config.c`: sound is off (`FXDevice = NumSoundCards`), which also stops
  the engine caching every sample at start-up, and the screen defaults to
  320x200.
* `Engine/tiles.c`: the DEF parse is a long C-only loop, so it yields every 32
  entries (`duke_platform_idle()`); without that the idle task is starved and
  the interrupt watchdog panics during start-up.
* `Engine/build.h`: `MAXSECTORS` is 1024 because E1L4 of the compacted episode
  has 557 sectors (the ESP32 size profile's 512 would overflow).
* `Engine/engine.c`: a sprite that is not in any sector carries `MAXSECTORS` as
  its marker; if one reaches `clipmove`, the clipper now refuses the move
  instead of reading past `sector[]` (an MMU entry fault, and a reboot). The
  sectors and sprites that reach the clipping functions are bounds-checked.
* `Game/game.c` `loadtmb()`: its 8 KB local buffer is static (`.bss`), the
  largest single frame in the engine.

## Running on its own task

The engine does not run on the MicroPython task. The loader creates a FreeRTOS
task for it (`mpos_core.start_task`, ABI 9, `MPOS_CORE_FLAG_WORKER`), and that
task's stack is the engine's own:

| Stack | Duke start-up | Notes |
|---|---|---|
| 16 KiB MicroPython task | cannot run the engine at all | |
| 24 KiB MicroPython task | the engine needs ~12 KB more | overflows in `compilecons` |
| 32 KiB MicroPython task | stack-overflow detected | |
| 48 KiB MicroPython task | works, ~24 KB free | the old arrangement |

The whole engine's start-up (`compilecons`, `enterlevel`) and its frames now
run on a **48 KiB worker** (peak use ~38 KB, 11 KB free - reached in play, not
at start-up), while the MicroPython task is back to **24 KiB** with 8 KB free.
Nothing of the engine's is on that stack any more.

A board whose DRAM is fragmented into blocks smaller than 48 KiB cannot give
the worker an internal stack - the fri3d 2026's largest free block is 32 KiB,
and 16/20/24/31 KiB stacks all overflow once the game is under way - so
`start_task` falls back to a PSRAM stack there. `PERFORMANCE.md` has the
canary results.

Two rules make the split safe, and they are the reason a worker core can be a
plain C engine:

* **the worker never enters MicroPython.** Every service it can call is
  implemented by the loader in C: the input ring (`post_key`), the asset it
  reads (the inflated GRP, sliced by pointer), the log (a line ring the main
  thread drains), the surface (its own buffers) and the clock (`esp_timer`).
  The only callbacks left are `present_band` (a no-op) and `frame_ready`;
* **the main thread keeps LVGL.** The worker renders into one of two buffers
  and calls `frame_ready()`; the activity shows the published buffer with
  `NativeDisplay.select_buffer()` + `flush()` and then gives it back with
  `task_presented()`. A buffer is only handed back after the pass that read it
  finished, so the engine is always drawing into the buffer nobody is showing.

The engine is pinned to core 0; the MicroPython task is on core 1.

## Firmware requirements

Two firmware changes are needed, both in the OS build this was tested with:

* the core loader's `log` trampoline handles a `"\x01yield"` sentinel in C
  with `vTaskDelay(1)`; a core cannot call FreeRTOS, and re-entering
  MicroPython from a deep engine frame to sleep is not safe (it panics). ABI 9
  adds a `yield()` callback for the same thing;
* `MICROPY_TASK_STACK_SIZE` is 24 KiB (from 16 KiB). The engine has its own
  stack now, so what the MicroPython task needs is its own frames: an LVGL pass
  runs on it (`lv.refr_now` from the frame loop) and at 16 KiB that pass leaves
  **32 bytes** free. At 24 KiB it leaves 8 KB. Measured, not guessed - see
  `PERFORMANCE.md`.

Measured on the MaTouch (ESP32-S3, 8 MB PSRAM): start-up (inflate the 2.6 MB
GRP, DEF/CON parse, level load, first-frame tiles) is about 7 s; gameplay runs
at **20-22 fps** at 320x200 with the picture transposed to the 200x320 logical
panel. A frame is ~47 ms of engine (render ~35 ms + palette convert ~12 ms);
the panel transfer (~22 ms) happens on the other core and overlaps it. The
engine's own frame time alone is ~30 ms when the MicroPython task is idle, so
the two cores do contend - `PERFORMANCE.md` has the numbers and why.

## Memory

The loader allocates, in order: the app's GRP buffer (Python, ~2.6 MB), the
core's arena (`.data` + `.bss`, 1.75 MB), and the engine's heap (2.5 MB).

`engine/Engine/build.h` is compiled with the ESP32 size profile
(`CONFIG_IDF_TARGET_ESP32` as well as `-S3`): 4096 sprites, 4096 walls, 512
sectors, 4096 cache objects. That is the profile the original ESP32 port used
and it fits the shareware maps; it halves `.bss` compared to the S3 defaults.

`.data` is supported even though Doom's core is dataless: the linker keeps the
section's VMA in the arena and its LMA in the blob's data region, and
`core_init` copies it before anything reads a global. This is why the engine
does not need a source rewrite to be loadable.

## Audio

The panels this targets (MaTouch, Waveshare) have no audio output. The engine
still calls `FX_*`/`MUSIC_*`, so `duke_audio.c` provides them as stubs and
`audio_mix()` returns silence. Porting audiolib (a 33k-line DOS mixer) or
synthesising the engine's 8-bit samples through the host's mixer is a separate
step; it is not on the load path.

## Build and install

```
./c_mpos/duke3d/build_duke_core.sh        # build_core/esp32s3.xip
```

A release ships the blob in the app as `esp32s3.xip` and the loader converts it
to a littlefs2e extent at install time. A development badge can instead have it
flashed into the reserved `retro-core` partition (0x710000):

```
esptool.py --port /dev/ttyUSB1 write_flash 0x710000 c_mpos/duke3d/build_core/esp32s3.xip
```

The app uses the file when it is present and the partition when it is not.
