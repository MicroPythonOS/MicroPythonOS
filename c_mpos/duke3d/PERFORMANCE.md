# Duke3D on the MaTouch: where the frame and stack time go

Measurements from the badge (ESP32-S3 @ 240 MHz, 8 MB octal PSRAM, 80 MHz SPI
ST7789, 240x320 logical panel), with the engine presenting a 200x320 surface.

## The two arrangements

The engine can run on the MicroPython task (ABI 8, `mpos_core.start`) or on a
task of its own (ABI 9, `mpos_core.start_task`). Everything below was measured
on the same blob and the same firmware, switching only that.

| | on the MicroPython task | on its own task |
|---|---|---|
| engine tick (render + convert) | 26.7 ms | 47 ms |
| panel present | 28 ms, serial | ~22 ms, on the other core |
| MicroPython task gap | ~2 ms | 0 |
| frame | ~57 ms -> **17.4 fps** | ~47 ms -> **20-22 fps** |
| stack the engine needs | 48 KiB *on the MicroPython task* | 48 KiB on its own task |

That is the whole trade: the engine gets slower, and the panel transfer stops
being added to it.

## Where the engine's time goes, on its own task

```
engine render + simulation   34-36 ms
palette convert + transpose  11-12 ms
present (announcing bands)    0.1 ms
buffer wait                   2-4 ms
--------------------------------------
engine tick                  47 ms   -> 20-22 fps
```

The engine profiles itself (`engine`, `convert`, `present`, `wait` in its 5 s
log line). `present` is ~0 because on a worker core the bands go into the
engine's own buffer and the activity transfers them; `wait` is the call that
hands the finished frame over and waits for the other buffer.

**The engine is 2x slower on its own task than it is alone.** With the
MicroPython task completely idle (`mpos.ui.task_handler.disable()`, so nothing
presents and the engine free-runs) the same engine renders at **33.5 fps,
30 ms a frame, render 22.8 ms, convert 7.2 ms**. The 17 ms a frame it loses
when the activity is running is the two cores sharing one L1 cache and one
PSRAM bus:

* the caches are shared between the cores, and both run code from flash (XIP),
  so the MicroPython task's LVGL passes evict the renderer's code lines;
* the engine's globals are the arena, 1.8 MB of **PSRAM**. The panel DMA
  streams 128 KB from the draw buffer per frame and LVGL copies the surface
  into it, so the renderer meets a lot of competing memory traffic.

Things that did **not** help, measured one at a time: dropping the task
handler period from 2 to 10 ms (+0.7 fps), turning the touch poll off (no
change), the old `duration = 200` fairness tweak (no change here, and it is now
applied only in the on-task mode), and skipping the panel flush entirely (no
change - which is what proves the cost is the other core's *code*, not the
transfer).

So the overlap pays for itself - 17.4 -> 21 fps - but it recovers the panel's
transfer time, not a second core's worth of rendering. A true 2x would need the
engine's code and data out of the shared cache and PSRAM, which is not
available on this chip.

## What the on-task arrangement cost

On the MicroPython task the engine's frame is serial: render 20.7 ms, convert
6 ms, present 28 ms. `present` is mostly the panel's DMA (a bare
`NativeDisplay` 200x320 flush measures 22.6 ms, i.e. 5.7 MB/s), which the core
sits and waits for.

Two changes had got it from 8.6 to 17.4 fps: the labelled touch overlay was
made a 6 s hint (7 labels redrawn over every invalidated band cost a third of
the frame), and the LVGL task handler's fairness wait was removed for the
foreground game (`duration = 200`, worth 14.3 -> 17.4). Both are still in
place for the on-task mode.

## Stack: this is what the separate task was for

`mpos_core.stack_high_water()` reports free bytes on the MicroPython task;
`mpos_core.task_stack()` on the worker.

| MicroPython task stack | free at the launcher | free with Duke running |
|---|---|---|
| 16 KiB | 2.4 KB | **32 bytes** (an LVGL pass in the frame loop) |
| 24 KiB | 10.6 KB | **8.2 KB** (the build that ships) |

With the engine on the MicroPython task the peak was the engine's start-up:
24 KiB left **340 bytes**, and 32 KiB hit FreeRTOS' overflow check during the
CON compile. With the engine on its own task the MicroPython task no longer
sees any of that, and what is left is its own deepest frame - the LVGL pass
that `flush()` runs - which needs 24 KiB. 16 KiB is 32 bytes short, so 20 KiB
would probably do, but the margin is not worth 4 KiB.

The worker's stack was chosen by canary, not by guess. Duke's **start-up is
not** its deepest path:

| worker stack | result |
|---|---|
| 16 KiB | overflow at start-up |
| 20 KiB | runs ~15 s, then overflow in play |
| 24 KiB | runs ~75 s, then overflow in play |
| 31 KiB | runs ~100 s, then overflow in play |
| 48 KiB | works, **11.4 KiB free** (peak use 37.8 KiB) |

So the engine has a path that needs about 38 KiB, and it is a gameplay path,
not the GRP/CON/level-load phase. `uxTaskGetStackHighWaterMark` is trustworthy
here: the 20-31 KiB runs each reported ~1.5 KiB free, which is exactly the
"nearly out" the overflow then confirmed.

38 KiB is more than some boards can hand out: the fri3d 2026's internal DRAM
is fragmented into ~32 KiB islands however much is free in total (largest free
block 32,768 at a clean boot, with 120 KiB free across the region), so
`xTaskCreatePinnedToCore` cannot make a 48 KiB stack there and Duke reports
`MemoryError: cannot create the core's task`. `start_task` therefore retries
with `MALLOC_CAP_SPIRAM` and the stack comes from PSRAM on such a board
(logged as `core: no 48 KiB internal block, stack in PSRAM`). That is slower
for a hot stack, but the engine's arena is already PSRAM and a playable game
beats one that cannot start.

So: 24 KiB for the OS, 48 KiB for a Duke-class engine, from internal RAM when
the board has a block that size and from PSRAM when it does not.
