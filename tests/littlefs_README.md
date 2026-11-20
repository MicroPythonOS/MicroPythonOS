# littlefs2e extent tests

`littlefs_test_extent.toml` is a littlefs test-runner case file (the same format as
upstream `littlefs/tests/*.toml`). It exercises:

- extent create/read/stat/rename/remove;
- alignment requests (1..8 blocks);
- `O_TRUNC` converting an extent back to an ordinary file;
- the disk version staying at 2.1 across an extent and a remount;
- a clean `LFS_ERR_NOCONTIG` when the filesystem has no large enough run.

## Running

The upstream runner is not vendored in this repository. `littlefs_run.sh` downloads
littlefs v2.11.3, copies the **patched** prefixed sources from
`lvgl_micropython/lib/micropython/lib/littlefs` (apply `patches/littlefs2e.patch`
first, which `build_mpos.sh` does), reverse-prefixes them to `lfs_*` for the
upstream runner, and runs the extent cases.

    ./tests/littlefs_run.sh

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
