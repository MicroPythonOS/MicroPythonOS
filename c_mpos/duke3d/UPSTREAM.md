# Upstream: off-screen tile views overflow the screen tables (ESP32 profile)

Status: **found while porting Duke3D to MicroPythonOS; not yet reported upstream.**
Upstream tree: `/home/user/sources/DukeNano3D/retro-go-for-DukeNano3D/duke3d-go`
(the DukeNano3D fork of Chocolate Duke3D / BUILD). The same functions exist in
`components/duke3d/Engine/`.

## What breaks

Duke draws some things into a **tile**, not the screen: a mirror
(`xyzmirror()` in `Game/premap.c`), the screen-tilt/save-thumbnail path in
`Game/game.c` (`displayrooms()`), and anything else that calls
`setviewtotile()`. That function sets the view from the **tile's** dimensions:

```c
void setviewtotile(short tilenume, int32_t tileWidth, int32_t tileHeight) {
    ...
    setview(0,0,tileHeight-1,tileWidth-1);       // xdimen=tileHeight, ydimen=tileWidth
    ...
    for (i=0; i<=tileWidth; i++) { ylookup[i] = j; j += tileHeight; }
}
```

On the ESP32 profile (`components/duke3d/Engine/build.h`) `MAXXDIM` is **320**
and `MAXYDIM` is **240**, but:

* `ylookup` is `int32_t ylookup[MAXYDIM+1]` (241 entries, build.h:198);
* `lastx` is `int32_t lastx[MAXYDIM]` (240 entries, engine.c:215);
* `uwall`/`dwall`/`swal`/`lwal`/`swplc`/`lplc`/`uplc`/`dplc`/`umost`/`dmost`
  are `[MAXXDIM+1]` (321 entries).

A tile view can be larger than both:

* the compacted shareware GRP declares a **128x400** mirror (the mirror in
  E1L2), so `tileWidth` is 400;
* the screen-tilt path calls `setviewtotile(MAXTILES-2, 320, 320)` when
  `ud.screen_tilting` is on and the view is rotated (`p->rotscrnang != 0`);
* the save thumbnail is 100x160, which fits.

The overflow then follows this chain:

1. `setviewtotile()` writes `ylookup[241..400]`, which lands in
   `numpages`/`ydim`/`xdim`/`tsprite` (the symbols immediately after
   `ylookup`), corrupting the renderer's view size;
2. `setviewback()` rebuilds `ylookup` up to `max(bakxsiz)` (`bakxsiz` is
   `max(xdimen, tileWidth)`, also 400 for the mirror), repeating the overflow;
3. `drawalls()` stores `lastx[y2++]` for `y2` up to the view height (`dmost`
   is `windowy2+1`), so the 400-row view writes 160 entries past `lastx` -
   into `globalhoriz`/`horizycent`/`horizlookup2`;
4. the next ordinary frame reads the corrupted tables: `hline()` indexes
   `horizlookup2` out of range, `hlineasm4()` gets a garbage texture pointer,
   and `setaspect()` can divide by a zeroed `xdim`.

On the badge it looked like four different crashes from one corruption:
`LoadProhibited` in `hline`/`hlineasm4`, `Dbus write to cache rejected` in
`vlineasm4`, `LoadStoreError`, and `IntegerDivideByZero` in `setaspect`. The
desktop profile (`MAXXDIM 1600`, `MAXYDIM 1200`) hides it because 400 < 1200.

## Reproduction

Any ESP32 build with this code should do it:

* play E1L2 and look at a mirror (the compacted GRP's mirror tile is 128x400);
  the crash comes within a minute of the mirror becoming visible, or
* enable screen tilting and rotate the view (`setviewtotile(..., 320, 320)`),
  or
* save a game (the 320x320 detail path, if `ud.detail == 0`).

On MicroPythonOS the panic dump plus
`xtensa-esp32-elf-addr2line -e c_mpos/duke3d/build_core/duke_core.elf <addr>`
named `hline`/`drawalls`; `c_mpos/duke3d/PERFORMANCE.md` and the Duke app log
have the frame context.

## Proposed patch

Keep the tile's own dimensions and pixels, but clamp the **view** to what the
screen-sized arrays can hold. This is what the MicroPythonOS port does (in
`c_mpos/duke3d/engine/Engine/tiles.c`); the same change applies upstream:

```c
void setviewtotile(short tilenume, int32_t tileWidth, int32_t tileHeight)
{
    int32_t i, j;
    int32_t viewW = tileWidth;      // rows the view will draw
    int32_t viewH = tileHeight;     // columns

    if (viewW > MAXYDIM) viewW = MAXYDIM;
    if (viewH > MAXXDIM) viewH = MAXXDIM;

    tiles[tilenume].dim.width = tileWidth;      // the tile keeps its size
    tiles[tilenume].dim.height = tileHeight;
    bakxsiz[setviewcnt] = max(xdimen, viewW);
    bakysiz[setviewcnt] = max(ydimen, viewH);
    ...
    setview(0, 0, viewH-1, viewW-1);
    ...
    for (i = 0; i <= viewW; i++) { ylookup[i] = j; j += tileHeight; }
    ...
}
```

and in `setviewback()` clamp the rebuild to the table:

```c
if (k >= MAXYDIM) k = MAXYDIM;
for (i=0; i<=k; i++) ylookup[i] = j, j += bytesperline;
```

Two smaller hardening changes, also in the port:

* `lastx[MAXYDIM]` → `lastx[MAXYDIM+1]` (the scan stores at `y2 == dmost`,
  which is `windowy2+1`);
* bound the `lastx[y1--]`/`lastx[y2++]` stores in `drawalls()` (and the
  `ny1`/`ny2` variants) to `0 .. MAXYDIM`.

Alternatively, if tile previews should be drawn in full, size `ylookup` for the
largest tile dimension (`MAXYLOOKUP 1024` used in the port) and do the same for
`lastx`; the per-column arrays would still need `MAXXDIM+1 >= tile width`, so a
tile wider than `MAXXDIM` must be clamped either way.

## Notes

* **`RG_PANIC` is not the upstream bug.** Upstream defines it as
  `rg_system_panic(...)` which calls `abort()` (components/retro-go/rg_system.c),
  so `reportandexit()` stops. The MicroPythonOS port originally stubbed
  `RG_PANIC` as a log call, which let `allocache` continue with an invalid best
  fit and corrupt `cac[]`; the port now aborts there and recovers from a full
  cache with a 1x1 transparent tile. No upstream change needed for that.
* The missing `tiles000.art` in the compacted GRP is a **data** issue (tiles
  89/92/93 in E1L2 are covered by PNG overrides or nothing). The 1x1
  transparent fallback is a port hardening, not an upstream requirement.
* Upstream owners: the repo is
  `retro-go-for-DukeNano3D` (DukeNano3D) under `DukeNano3D/`; the BUILD engine
  fork is in `components/duke3d/Engine/`. Report with the crash chain, the
  128x400 mirror / 320x320 tilt views, and the patch above; the ESP32 profile
  is the affected one.

## Verification after patching

1. Build the ESP32 profile and play E1L2's mirror; no `hline` panic, no
   `setaspect` divide-by-zero.
2. Enable screen tilting, rotate the view, and save a game (the 320x320 view).
3. Add a canary around `ylookup`/`lastx` in a debug build and assert the view
   never writes outside them (or run under the desktop profile with a small
   `MAXYDIM` to reproduce).
