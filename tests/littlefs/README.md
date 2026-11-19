# littlefs2e extent tests

`test_extent.toml` is a littlefs test-runner case file (the same format as
upstream `littlefs/tests/*.toml`). It exercises:

- extent create/read/stat/rename/remove;
- alignment requests (1..8 blocks);
- `O_TRUNC` converting an extent back to an ordinary file;
- the lazy disk-version upgrade (2.1 -> 2.0xE000) and remount;
- a clean `LFS_ERR_NOCONTIG` when the filesystem has no large enough run.

## Running

The upstream runner is not vendored in this repository. `run.sh` downloads
littlefs v2.11.3, copies the **patched** prefixed sources from
`lvgl_micropython/lib/micropython/lib/littlefs` (apply `patches/littlefs2e.patch`
first, which `build_mpos.sh` does), reverse-prefixes them to `lfs_*` for the
upstream runner, and runs the extent cases.

    ./tests/littlefs/run.sh

To run the full upstream suite as well:

    cd tmp/littlefs-tests
    make test NO_COV=1 -j4

The full suite is the gate for any change to `lfs2_alloc`, `fs_traverse`,
metadata commits, or the runtime disk-version logic.

`test_compat` is not applicable as written: its minor-incompatibility cases
assume the stock 2.1 maximum, while littlefs2e deliberately accepts
2.0xE000. The fork's version behaviour is covered by `test_extent.toml`
(2.1 format, upgrade on the first extent, 2.0xE000 after remount). Run the
rest with:

    TESTS=$(ls tests/test_*.toml | grep -v test_compat | tr '\n' ' ')
    make test NO_COV=1 -j4 TESTFLAGS="$TESTS"
