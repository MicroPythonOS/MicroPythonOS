# Upstream: off-screen tile views overflow the screen tables (ESP32 profile)

Status: **the death view was fixed upstream in `9c46dd9e`; the remaining
bounds are proposed in
[DynaMight1124/retro-go#31](https://github.com/DynaMight1124/retro-go/pull/31).**
Upstream tree: `/home/user/sources/DukeNano3D/retro-go-for-DukeNano3D/duke3d-go`
(the DukeNano3D fork of Chocolate Duke3D / BUILD).

## What breaks

Duke draws a few things into a **tile**, not the screen:

* the security camera's monitor (`xyzmirror()` in `Game/premap.c`, a
  `VIEWSCREEN` sprite — 96x96);
* the screen-tilt view used while the player is dead (`Game/game.c`,
  `displayrooms()` — 200x320 upright, **320x320** once tilted);
* the save thumbnail (100x160).

They all call `setviewtotile()`, which sets the view from the **tile's**
dimensions:

```c
void setviewtotile(short tilenume, int32_t tileWidth, int32_t tileHeight) {
    ...
    setview(0,0,tileHeight-1,tileWidth-1);   // x extent = tileHeight, y = tileWidth
    ...
    for (i=0; i<=tileWidth; i++) { ylookup[i] = j; j += tileHeight; }
}
```

On the ESP32 profile (`components/duke3d/Engine/build.h`) `MAXXDIM` is **320**
and `MAXYDIM` was **240** until `9c46dd9e` raised it to `INTERNAL_RES_W`
(320). The renderer's tables are:

* `ylookup` is `int32_t ylookup[MAXYDIM+1]` (321 entries now, 241 before);
* `lastx` is `int32_t lastx[MAXYDIM]` (320 entries now, 240 before);
* `uwall`/`dwall`/`swal`/`lwal`/`swplc`/`lplc`/`uplc`/`dplc`/`umost`/`dmost`
  are `[MAXXDIM+1]` (321 entries).

With `MAXYDIM` at 240 the 320-row tilt view wrote 80 entries past both tables:

1. `setviewtotile()` writes `ylookup[241..320]`, which lands in
   `numpages`/`ydim`/`xdim`/`tsprite` (the symbols immediately after
   `ylookup`), corrupting the renderer's view size;
2. `setviewback()` rebuilds `ylookup` up to `max(bakxsiz)` (`bakxsiz` is
   `max(xdimen, tileWidth)`, 320 for the tilt view), repeating the overflow;
3. `drawalls()` stores `lastx[y2++]` for `y2` up to the view height (`dmost`
   is `windowy2+1`), so the 320-row view wrote 80 entries past `lastx` into
   `globalhoriz`/`horizycent`/`horizlookup2`;
4. the next ordinary frame reads the corrupted tables: `hline()` indexes
   `horizlookup2` out of range, `hlineasm4()` gets a garbage texture pointer,
   and `setaspect()` divides by a zeroed `xdim`.

On the badge that looked like four different crashes from one overflow:
`LoadProhibited` in `hline`/`hlineasm4`, `Dbus write to cache rejected` in
`vlineasm4`, `LoadStoreError`, and `IntegerDivideByZero` in `setaspect`. The
MicroPythonOS port hit the same view but crashed rather than just corrupted,
for two reasons: its BSS puts `globalhoriz` 240 bytes after `lastx` (the
native build puts `bakdmost`/`bakumost` there), and its engine copy predates
`9c46dd9e`, so it kept `MAXYDIM` at 240.

`9c46dd9e` ("Fixed death glitch and also FPS cap", DynaMight) removed the
80-entry overrun by sizing the tables for the tilt view. Two smaller issues
remain, and are what PR #31 fixes:

* the scans store at `dmost`, i.e. `windowy2+1`, so a full-height view still
  writes one row past `lastx`;
* a tile view larger than the screen (a GRP or mod with a bigger
  camera/monitor texture) is still unchecked, and `setviewback()` then
  rebuilds `ylookup` past its table.

**The compacted GRP.** It keeps `TILE095.PNG` at 128x400 (the original ART's
tile 95 has the same size), and the port primes tile dimensions from the PNG
header, but that tile is a map texture, not a tile-view target; the compacted
ART sets themselves have no entry taller than 240.

## Reproduction

Any ESP32 build with the pre-`9c46dd9e` tables does it:

* play and die with screen tilting on (the default): `setviewtotile(...,
  320, 320)` runs on every frame while the tilt view is up;
* or give the engine a GRP whose camera/monitor texture (`VIEWSCREEN`) is
  larger than the screen;
* saving a game uses the 100x160 thumbnail, which fits.

On MicroPythonOS the panic dump plus
`xtensa-esp32-elf-addr2line -e c_mpos/duke3d/build_core/duke_core.elf <addr>`
named `hline`/`drawalls`; `c_mpos/duke3d/PERFORMANCE.md` and the Duke app log
have the frame context.

## Proposed patch

Keep the tile's own dimensions and pixels, but clamp the **view** to what the
screen-sized arrays can hold. This is what the MicroPythonOS port does (in
`c_mpos/duke3d/engine/Engine/tiles.c`), and what PR #31 applies upstream:

```c
void setviewtotile(short tilenume, int32_t tileWidth, int32_t tileHeight)
{
    int32_t i, j;
    int32_t viewRows = tileWidth;  /* the view's y extent (the tile's height) */
    int32_t viewCols = tileHeight; /* the view's x extent (the tile's width) */

    if (viewRows > MAXYDIM) viewRows = MAXYDIM;
    if (viewCols > MAXXDIM) viewCols = MAXXDIM;
    if (viewCols > MAXYDIM) viewCols = MAXYDIM; /* ylookup is column-indexed */

    tiles[tilenume].dim.width = tileWidth;      // the tile keeps its size
    tiles[tilenume].dim.height = tileHeight;
    bakxsiz[setviewcnt] = max(xdimen, viewCols);
    bakysiz[setviewcnt] = max(ydimen, viewRows);
    ...
    setview(0, 0, viewCols-1, viewRows-1);
    ...
    for (i = 0; i <= viewCols; i++) { ylookup[i] = j; j += tileHeight; }
    ...
}
```

and in `setviewback()` clamp the rebuild to the table and restore the span
offset:

```c
if (k > MAXYDIM) k = MAXYDIM;
for (i=0; i<=k; i++) ylookup[i] = j, j += bytesperline;
viewoffset = windowy1*bytesperline + windowx1;
frameoffset = frameplace+viewoffset;
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
* Upstream owners: the engine fork is in `components/duke3d/Engine/` of
  `retro-go-for-DukeNano3D`; Duke support itself is
  [ducalex/retro-go#289](https://github.com/ducalex/retro-go/pull/289), and the
  tile-view patch is
  [DynaMight1124/retro-go#31](https://github.com/DynaMight1124/retro-go/pull/31).

## Verification after patching

1. Die with screen tilting on: the death view and the pause menu over it reach
   the screen, with no `hline` or `setaspect` fault.
2. A GRP whose camera texture is larger than the screen renders clipped, with
   no corruption.
3. Add a canary around `ylookup`/`lastx` in a debug build and assert the view
   never writes outside them (or run a profile with a small `MAXYDIM` to
   reproduce).
