# littlefs2e extent files

`patches/littlefs2e.patch` turns the vendored littlefs into **littlefs2e**:
littlefs v2.11.3 plus a third file-data representation for contiguous,
immutable runs ("extents").

## On disk

- New struct tag `LFS2_TYPE_EXTSTRUCT` (`0x203`):

      struct lfs2_ext {
          uint32_t head;    // first block of the run
          uint32_t count;   // padded run length in blocks
          uint32_t length;  // payload bytes
          uint32_t crc;     // optional payload CRC
          uint32_t flags;
      };

  An extent file has no CTZ or inline data tag; the extent tag is its data.
  `lfs2_fs_traverse_()` counts the whole run, so it is "used" to the
  allocator, `fs_size()` and `statvfs()`. Deleting or truncating the file
  frees the run (littlefs's drop-on-the-floor deallocation).

- Format and new extents use the standard disk **2.1** (`LFS2_DISK_VERSION`).
  The extent tag is unknown to stock littlefs: stock can mount the image, but
  its allocator treats the extent's blocks as free, so stock tools must be
  read-only. The stored CRC lets a consumer detect a stock write or flash
  corruption before using the extent. There is no separate extent disk
  version and no legacy one to mount.

## Invariants

- An extent is immutable. `open(path, "wb")` (O_TRUNC) deletes the extent tag
  and continues as an ordinary littlefs file, which is how an app update
  replaces a core.
- The run is reserved before it is written: `lfs2_ext_reserve()` builds a
  used-block map, finds a run whose start is `align`-block aligned, erases it
  and marks it in `lfs2_t.ext_map`. `lfs2_alloc()` and `lfs2_alloc_scan()`
  skip that map until `lfs2_ext_commit()` or `lfs2_ext_abort()`, so metadata
  commits during creation cannot land inside the run.
- Alignment is a caller parameter: 1 block for an ordinary contiguous file,
  16 blocks (64 KiB with 4 KiB blocks) for an XIP window the ESP32 MMU can
  map.
- The extent bookkeeping uses `LFS2_EXT_MAP_MAX` (1024 bytes) in `lfs2_t`,
  not the heap: the firmware builds littlefs with `LFS2_NO_MALLOC`. This
  covers filesystems up to 8192 blocks (32 MiB at 4 KiB).
- Power loss: payload first, then the tag. A crash leaves either the old
  file, or no tag and an unreferenced run; never a tag that points at a
  partially written run.

## Defrag

`lfs2_ext_defrag_begin()` / `step()` / `result()` / `abort()` plan and perform
the whole operation in C, one bounded unit per step (a directory fetch, one
entry, one relocated pair, one moved file or eight erased blocks).
`lfs2_ext_defrag()` is the synchronous wrapper. A step reports a phase
(`SPACE`, `MOVE`, `ERASE`) and a best-effort percent, so a caller that owns a UI
can await between steps and show "Defragmenting storage... 60%" instead of
freezing for the whole operation. Only one run is active at a time; a mount
discards a stale one (a non-local exit, such as a power-loss injection, would
otherwise leave it behind).

1. A used map ranks aligned windows by how many used blocks they hold.
2. A window holding an extent, the root pair or a split directory's **tail**
   pair is rejected. A window holding an open file's blocks is dropped and the
   next candidate is tried: a sideloaded engine is defragmented while the app
   still has its WAD open, and one busy window must not abort the whole run.
3. `lfs2_ext_clear_window()` excludes the window from the allocator, relocates
   every directory whose pair intersects it (`lfs2_ext_relocate_dir()`), then
   copies each occupying ordinary file to `<name>.dfg` and renames it back.
   Occupants are processed in rounds, so a window with many files needs no
   large table.
4. The cleared window is erased and reserved exactly as `lfs2_ext_reserve()`
   does, so `lfs2e.commit()` can turn it into an extent. Rounds are capped by
   the window size (`count / occupants + 2`), not a fixed number: an 80-block
   window full of one-block files needs ten rounds.

`lfs2_ext_relocate_dir()` compacts the directory into a fresh metadata block,
repoints the parent (following the chain when the parent relocates too) and
unlinks the old pair: copy, switch, orphan, never move in place. A compaction
moves only one half of the pair (`{a,b}` becomes `{c,a}`), so the call repeats
while either block is inside an active exclusion.

The window scan walks directories **by pair**, from `DIRSTRUCT` tags, not by
path. On the badge every tag read reaches flash through a Python block-device
callback, and a path lookup costs a full metadata scan per component: the
path-based version took 43 s to clear one 48-block window on a MaTouch, while
the pair walk on the same fixture is 18 s. One `lfs2_dir_get` per entry covers
every data tag (the 0x700 mask matches DIRSTRUCT, INLINE, CTZ and EXTSTRUCT;
`type3` tells them apart), and the name of an entry is read only when the
window keeps it, because each of those reads is another full metadata scan.

The cost is the device, not the algorithm. On a MaTouch, a 48-block window on
a 7 MiB filesystem with ~270 four-block files took 18.3 s before the VFS work
below and 10.8 s after. The split is now ~2 s scanning, ~3.4 s moving the
files in the window and ~2.1 s erasing it. Erasing 48 blocks at ~43 ms each is
a floor, and the moves are write-bound: the badge writes at ~58 KB/s (a 16 KiB
copy costs ~290 ms however it is chunked) and reads at ~1.5 MB/s.

The VFS is the lever, not the step machine. With `cache_size` at the upstream
default of a quarter block, every metadata block crosses the Python block
device four times and every 16 KiB copy flushes its program cache eight times.
`patches/lfs2_cache_size.patch` makes `cache_size` the block size: on the same
fixture the scan drops from 4.8 s to 2.0 s and the moves from 6.0 s to 3.4 s
(the erase phase does not change). That patch is RAM only. The image builder
(`-r 256 -m 1024`) and the mount (`readsize=256, progsize=256`) are untouched,
and `inline_max` is clamped to `block_size/8` (512 bytes) on both sides, so the
layout, the inline threshold and the space used stay identical. The price is
memory: 6 KiB more for the two mount caches and one block per open file (the
VFS file object embeds its own cache; ~4.2 KiB against ~1.2 KiB before, out of
a 7.4 MiB PSRAM heap).

The defragmenter's four run buffers (two file caches, the copy chunk and a
private read cache for the per-entry data-block walks) live in its
single-flight state rather than on the C stack: the firmware builds littlefs
with `LFS2_NO_MALLOC`, and another 16 KiB of stack under the Python block
device call would not fit the MicroPython task stack.

A split directory's tail pair cannot be relocated this way: `lfs2_fs_parent()`
finds a child through its `DIRSTRUCT` entry, while a tail is referenced by a
`TAIL` tag in the head pair. A window holding one is skipped, which is the one
remaining ceiling on the largest run. Lifting it means either rewriting the
head's `TAIL` tag to point at a freshly allocated tail pair, or rebuilding the
head and its whole tail chain into new pairs.

`mpos.extent` is policy only (alignment, CRC, streaming). `Writer` calls
`lfs2e.defrag()` when `reserve()` reports `LFS_ERR_NOCONTIG`;
`open_writer()` runs the steps with `await asyncio.sleep(0)` between them, and
the installer awaits it with a progress callback. Doom's launch screen, which
has no event loop to yield to, uses `ensure(progress=...)`: the hook calls
`lv.refr_now()` between steps, the same way its other launch messages work.

## MicroPython glue

- `extmod/vfs_lfs.c/h`: `mp_vfs_lfs2_root_lfs2()`, because the mounted
  `VfsLfs2` instance is not reachable from Python.
- `c_mpos/src/lfs2e.c`: the `lfs2e` built-in module used by
  `internal_filesystem/lib/mpos/extent.py`.
- `scripts/build_mpos.sh` applies the patch to the nested MicroPython tree
  before every target build.

## Tests

`tests/littlefs_run.sh` downloads the v2.11.3 test runner, reverse-prefixes
the patched `lfs2_*` sources and runs two case files:

- `tests/littlefs_test_extent.toml` — extent create/read/stat/rename/remove,
  alignment, disk version, `LFS_ERR_NOCONTIG`;
- `tests/littlefs_test_relocate.toml` — metadata relocation (contents, root
  refusal, the two-pass window clear, the parent chain through injected bad
  blocks, a split directory's tail pinning a window) and the defragmenter
  (fragmented image, budget and extent pinning, and a 7 MiB badge-sized image).
  Two cases are `reentrant`, so the runner replays them under power loss.

Helpers live in `tests/relocate_test_helpers.h` and are injected with
`--include`. The script runs `-P none,linear` plus a few fixed two-cut
sequences. **Do not use `-Pexhaustive`**: it forks a full copy of the block
device at every cut point and keeps the branch tree, which needs gigabytes for
a case with a few dozen writes (it has OOM-killed a 7.7 GB machine).
