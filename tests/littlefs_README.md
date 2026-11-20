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
