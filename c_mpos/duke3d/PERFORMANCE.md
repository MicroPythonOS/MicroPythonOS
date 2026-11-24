# Duke3D on the MaTouch: where the frame and stack time go

Measurements from the badge (ESP32-S3 @ 240 MHz, 8 MB octal PSRAM, 80 MHz SPI
ST7789, 240x320 logical panel), with the engine presenting a 200x320 surface.

## Frame budget at the current best (overlay hidden, fairness gap removed)

```
engine render + simulation   ~20.7 ms  (about 2 game tics at 30 tics/s)
convert palette + transpose    6.0 ms  (64k pixels, RGB565)
panel present (LVGL + SPI)    21-28 ms (22.6 ms measured for a bare 200x320
                                        surface, so this is the panel floor)
task handler / OS gap          ~2  ms
--------------------------------------------
total                          57   ms -> 17.4 fps
```

The engine counter in the log is the whole `tick()` and therefore contains the
convert and present parts; the three numbers above are the split inside it.

The 2 ms gap is what is left after the game raises the task handler's fairness
threshold. Before that the handler waited a quarter of the previous 50-60 ms
pass (about 13 ms) before scheduling the next one; at 14.3 fps that wait was
~20 ms including the timer period and VM scheduling. The app sets
`mpos.ui.task_handler.duration = 200` on resume and restores 2 on pause/stop;
the timer period (and therefore the REPL's share between passes) is unchanged,
only the extra wait is removed. That alone was 14.3 -> 17.4 fps.

For comparison, a bare `NativeDisplay` 200x320 flush is 22.6 ms, 240x320 is
27.9 ms. The 128 KB transfer is ~5.7 MB/s, i.e. the panel bus is the floor for
presentation; it is not LVGL overhead.

## What the overlay costs

The full touch overlay (7 outlines + 7 labels) sits over the picture. Every
present invalidates the image bands, so LVGL redraws the labels on top of them
every frame. While it is visible the frame costs ~130 ms (5-8 fps); after it
hides (6 s hint, or first touch) the frame drops to 70 ms (14.3 fps). That is
why the activity now hides it after 6 s and shows it again on resume.

## Things tried, and their effect

| Change | Result |
|---|---|
| One LVGL pass per frame (invalidate all bands, flush on the last) | no measurable change; the panel transfer, not the pass count, is the cost |
| Raise the task handler fairness threshold (`duration=200`) | **+3.1 fps** (14.3 -> 17.4); the ~20 ms gap was the fairness wait after all |
| `ud.shadows = 0` | no measurable change |
| Tile cache reserve 640 -> 320 KB (cache 661 -> 981 KB) | no change *at the spawn*: `tile decodes 0` during gameplay, the cache already holds this view |
| `ud.detail = 0` (half-resolution renderer) | **crashes**: integer divide by zero in `setaspect` through this port's low-detail path; needs a fix before it can be used |
| Hiding the overlay after 6 s | **+5.7 fps** (8.6 -> 14.3) |

## Why the native duke3d-go is faster

The native port does not pay the last two rows of the budget above:

* it has no LVGL between the engine and the panel: `rg_display_submit` converts
  the 8-bit palette surface and hands it to the display driver directly, with
  two buffers, from the same thread that renders;
* it has no MicroPython task handler in the loop, so there is no ~20 ms
  scheduling/fairness gap and no Python callback per band.

At 14.3 fps the remaining gap to its 15-30 fps is mostly the ~20 ms OS gap and
the LVGL present path. The engine's own 22.6 ms is already in the native
ballpark.

## The next two levers, in order of value

1. **Let the game own the panel path again.** A `present_area`-style direct
   write (the engine's surface -> the display's `tx_color`, with the OS bar and
   overlay drawn by LVGL only when visible) would remove LVGL from the per-frame
   path. This is what the old Breakout did and what the notes say flickers when
   LVGL also refreshes; the supported version would be a `NativeDisplay` mode
   that hands the dirty bands to the bus itself, with LVGL paused only while the
   game is full-screen. Expect present 21 -> 12-15 ms.
2. **Run the engine off the MicroPython task.** A dedicated engine task (with
   its own stack) that renders into the surface while the main thread presents
   removes the ~20 ms task-handler gap *and* the 32/48 KB stack requirement on
   the MicroPython task. It needs the ABI callbacks split into "C only during
   tick" (present = mark bands dirty, input = a lock-free queue) so the engine
   never re-enters Python from its own task. This is the architecturally
   correct fix for both problems.

The engine-side items left are smaller: the tile cache matters on maps with
more unique textures (the spawn of E1L1 has none), and the low-detail path
needs the divide fixed before it is usable.

## The stack question

`mpos_core.stack_high_water()` reports free bytes on the MicroPython task.

| Stack | Free after Duke start-up | Free at the launcher |
|---|---|---|
| 16 KiB | cannot run Duke | ~4 KB |
| 24 KiB | **340 bytes** | 12,052 bytes |
| 32 KiB | **stack-overflow detected during compilecons** | 18,772 bytes |
| 48 KiB | ~24 KB (working build) | ~28 KB |

The peak is reached during **start-up**, not gameplay: the HWM is already 340
bytes right after `engine.start()` returns, and a 5-minute game does not lower
it. The deepest marked phases are `startup` -> `compilecons` -> `enterlevel`
(the GRP/CON parse and the first level load), on top of the ~12 KB the launcher
itself uses and the ~10 KB of Python/activity/loader frames that call into the
engine.

So 24 KiB is not feasible for Duke as it stands: it leaves less than half a
kilobyte, and a menu, a level change or a save would overflow. 32 KiB did not
survive the start-up in testing either (FreeRTOS' canary was hit during
`compilecons`, even though the high-water mark on the 24 KiB build reported 340
bytes free - the two measurements disagree, and the safe reading is the
overflow). The desktop's 24 KB is a different port with a different caller
chain and is not comparable. 48 KiB is the working build.

Getting Duke under 24 KiB needs either the start-up peak cut by ~10 KB or the
dedicated engine task above, which takes the engine off this stack entirely.
Until then the pragmatic choice is **48 KiB for a build that includes this
engine**, or 24 KiB for a system without it.
