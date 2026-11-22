# littlefs2e extent tests

The filesystem half of littlefs2e is a fork of littlefs v2.11.3,
[`third_party/littlefs2e`](https://github.com/MicroPythonOS/littlefs_with_extents_and_defrag),
consumed as a submodule. Its cases live with the fork, where they run against
unprefixed `lfs.c` exactly as upstream does:

- `tests/test_extent.toml` — extent create/read/stat/rename/remove, alignment
  requests (1..8 blocks), `O_TRUNC` converting an extent back to an ordinary
  file, the disk version staying 2.1 across an extent and a remount, and a
  clean `LFS_ERR_NOCONTIG` when the filesystem has no large enough run.
- `tests/test_extent_defrag.toml` — metadata-pair relocation and the
  defragmenter: contents and remount after a relocation, the root refusal, the
  two-pass window clear, the parent chain (forced through injected bad blocks),
  a split directory's tail pair pinning a window, a fragmented image that the
  defragmenter must clear and reserve, budget/extent refusals, a 7 MiB
  badge-sized image, the resumable `begin`/`step` driver (phase order, a second
  begin refused) and a window whose occupants are all one-block files (the
  round budget). Two cases are `reentrant`, which makes the runner replay them
  under power loss.

## Running

`littlefs_run.sh` runs those two case files inside the submodule, so no copy
and no download are involved. It needs the `toml` module
(`python3 -m pip install toml`) for the fork's runner:

    ./tests/littlefs_run.sh

Power loss: the script runs `-P none,linear` (one cut at every write offset)
plus a few fixed two-cut sequences. **Never use `-Pexhaustive` here**: it forks
a copy of the whole block device at every cut point and keeps the branch tree,
which needs gigabytes — it has OOM-killed a 7.7 GB machine on these cases.

To run the full upstream suite (including these cases) as well:

    ./tests/littlefs_run.sh --full

`test_compat` is part of the full run: the fork keeps the stock 2.1 disk
version, including its minor-version compatibility rules.

The full suite is the gate for any change to `lfs_alloc`, `fs_traverse`,
metadata commits, or the version checks.

## Updating littlefs2e

`scripts/sync_littlefs2e.sh` prefixes `third_party/littlefs2e` (`lfs_*` →
`lfs2_*`) into `lvgl_micropython/lib/micropython/lib/littlefs`, and
`build_mpos.sh` runs it before every build. `scripts/sync_littlefs2e.sh
--check` reports whether the tree has drifted from the pin.

To take a new littlefs release: rebase the fork's `extents` branch onto the
upstream tag, run `./tests/littlefs_run.sh --full` there, tag it, then move the
submodule pointer. No patch is regenerated; the pointer is the version.

## Stock compatibility

`littlefs_stock_mount.sh` builds the same test program twice — once against the
fork, once against stock v2.11.3 — and runs one image through both:

1. the fork formats a 2.1 image with a normal file and a 9000-byte extent, and
   its CRC reads back intact;
2. stock littlefs mounts that image, reads the normal file, and sees the
   extent's inode as a file (it does not know the extent struct, so it reports
   no size);
3. a stock write that fills the free space lands on the extent's blocks, and the
   fork's CRC check catches it.

That last step is the reason for the CRC and for the "stock tools are read-only"
rule: stock littlefs treats an extent's blocks as free space and will overwrite
the payload.

    ./tests/littlefs_stock_mount.sh
