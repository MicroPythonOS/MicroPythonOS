# littlefs2e extent tests

`littlefs_test_extent.toml` is a littlefs test-runner case file (the same format as
upstream `littlefs/tests/*.toml`). It exercises:

- extent create/read/stat/rename/remove;
- alignment requests (1..8 blocks);
- `O_TRUNC` converting an extent back to an ordinary file;
- the disk version staying at 2.1 across an extent and a remount;
- a clean `LFS_ERR_NOCONTIG` when the filesystem has no large enough run.

`littlefs_test_relocate.toml` covers metadata-pair relocation and the
defragmenter: contents and remount after a relocation, the root refusal, the
two-pass window clear, the parent chain (forced through injected bad blocks), a
split directory's tail pair pinning a window, a fragmented image that the
defragmenter must clear and reserve, budget/extent refusals, a 7 MiB
badge-sized image, the resumable `begin`/`step` driver (phase order, a second
begin refused) and a window whose occupants are all one-block files (the round
budget). Its helpers live in `relocate_test_helpers.h` and are
injected into every generated case file with `--include` (so that header
includes `runners/test_runner.h` itself). Two cases are `reentrant`, which makes
the runner replay them under power loss.

## Running

The upstream runner is not vendored in this repository. `littlefs_run.sh` downloads
littlefs v2.11.3, copies the **patched** prefixed sources from
`lvgl_micropython/lib/micropython/lib/littlefs` (apply `patches/littlefs2e.patch`
first, which `build_mpos.sh` does), reverse-prefixes them to `lfs_*` for the
upstream runner, and runs the extent and relocation cases.

    ./tests/littlefs_run.sh

Power loss: the script runs `-P none,linear` (one cut at every write offset)
plus a few fixed two-cut sequences. **Never use `-Pexhaustive` here**: it forks
a copy of the whole block device at every cut point and keeps the branch tree,
which needs gigabytes — it has OOM-killed a 7.7 GB machine on these cases.

To run the full upstream suite as well:

    cd tmp/littlefs-tests
    make test NO_COV=1 -j4

`test_compat` is part of the full run: the fork keeps the stock 2.1 disk
version, including its minor-version compatibility rules.

The full suite is the gate for any change to `lfs2_alloc`, `fs_traverse`,
metadata commits, or the version checks.

## Stock compatibility

`littlefs_stock_mount.sh` builds the same test program twice - once against the
fork, once against stock v2.11.3 - and runs one image through both:

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
