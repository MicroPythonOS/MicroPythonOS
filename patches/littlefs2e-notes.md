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

`mpos.extent.defrag(need, align)` (and the C helpers) plans a window:
`lfs2_ext_block_maps()` gives used and metadata-pair bitmaps,
`lfs2_ext_file_blocks()` gives per-file ownership. It picks the aligned
window with the smallest total file size, excludes it with
`lfs2_ext_exclude()`, moves the occupying normal files with copy+rename
(atomic per file), clears the exclusion and checks `lfs2_ext_largest_run()`.
Metadata pairs and existing extents are never moved. The budget is derived
from the extent size, filesystem size and free space; if no window fits, the
caller gets `LFS_ERR_NOCONTIG`.

## MicroPython glue

- `extmod/vfs_lfs.c/h`: `mp_vfs_lfs2_root_lfs2()`, because the mounted
  `VfsLfs2` instance is not reachable from Python.
- `c_mpos/src/lfs2e.c`: the `lfs2e` built-in module used by
  `internal_filesystem/lib/mpos/extent.py`.
- `scripts/build_mpos.sh` applies the patch to the nested MicroPython tree
  before every target build.

## Tests

`tests/littlefs_run.sh` downloads the v2.11.3 test runner, reverse-prefixes
the patched `lfs2_*` sources and runs `tests/littlefs_test_extent.toml`. The
rest of the upstream suite (including `test_compat`, now that the format is
2.1) passes as well.
