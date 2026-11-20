/*
 * The same littlefs image, written by the littlefs2e fork and read by stock
 * littlefs v2.11.3.
 *
 * The fork stores an extent file as an ordinary inode with one extra struct
 * attribute (LFS_TYPE_EXTSTRUCT, 0x203) that stock littlefs does not know.
 * A stock mount must therefore still: see the normal files, mount the 2.1
 * disk, and treat the extent's blocks as free space. That last part is why the
 * extent stores a CRC: a stock write can land on top of the payload.
 *
 * Built twice by littlefs_stock_mount.sh, with -DHAVE_EXTENTS against the fork.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lfs.h"
#include "bd/lfs_filebd.h"

#define BLOCK_SIZE 512
#define BLOCK_COUNT 256
#define EXTENT_SIZE 9000

static const char *image_path;
static lfs_t lfs;
static struct lfs_config cfg;
static lfs_filebd_t bd;
static const struct lfs_filebd_config bdcfg = {
    .read_size = 64,
    .prog_size = 64,
    .erase_size = BLOCK_SIZE,
    .erase_count = BLOCK_COUNT,
};

static int mount_image(int format) {
    memset(&cfg, 0, sizeof(cfg));
    memset(&bd, 0, sizeof(bd));
    cfg.context = &bd;
    cfg.read = lfs_filebd_read;
    cfg.prog = lfs_filebd_prog;
    cfg.erase = lfs_filebd_erase;
    cfg.sync = lfs_filebd_sync;
    cfg.read_size = 64;
    cfg.prog_size = 64;
    cfg.block_size = BLOCK_SIZE;
    cfg.block_count = BLOCK_COUNT;
    cfg.cache_size = 256;
    cfg.lookahead_size = 16;
    cfg.block_cycles = 100;

    int err = lfs_filebd_create(&cfg, image_path, &bdcfg);
    if (err) {
        printf("bd create: %d\n", err);
        return err;
    }
    if (format) {
        err = lfs_format(&lfs, &cfg);
        if (err) {
            printf("format: %d\n", err);
            return err;
        }
    }
    err = lfs_mount(&lfs, &cfg);
    if (err) {
        printf("mount: %d\n", err);
    }
    return err;
}

static int unmount_image(void) {
    int err = lfs_unmount(&lfs);
    lfs_filebd_destroy(&cfg);
    return err;
}

static int write_normal_file(void) {
    lfs_file_t file;
    int err = lfs_file_open(&lfs, &file, "hello",
                            LFS_O_WRONLY | LFS_O_CREAT | LFS_O_TRUNC);
    if (err) {
        return err;
    }
    err = lfs_file_write(&lfs, &file, "hello", 5);
    if (err < 0) {
        return err;
    }
    return lfs_file_close(&lfs, &file);
}

static int create_image(void) {
    remove(image_path);
    int err = mount_image(1);
    if (err) {
        return err;
    }
    err = write_normal_file();
    if (err) {
        printf("normal file: %d\n", err);
        return err;
    }
#ifdef HAVE_EXTENTS
    static uint8_t data[EXTENT_SIZE];
    for (int i = 0; i < EXTENT_SIZE; i++) {
        data[i] = (uint8_t)(i * 7);
    }
    lfs_ext_t ext;
    err = lfs_ext_reserve(&lfs, sizeof(data), 1, &ext);
    if (err) {
        printf("reserve: %d\n", err);
        return err;
    }
    err = lfs_ext_write(&lfs, 0, data, sizeof(data));
    if (err) {
        printf("write: %d\n", err);
        return err;
    }
    // The extent's stored CRC is the caller's; the app computes it over the
    // payload it wrote (as mpos.extent does) so a later reader can verify it.
    err = lfs_ext_commit(&lfs, "core.bin", lfs_crc(0, data, sizeof(data)));
    if (err) {
        printf("commit: %d\n", err);
        return err;
    }
#else
    printf("ERROR: the create/check side is the fork; build it with -DHAVE_EXTENTS\n");
    return 1;
#endif
    return unmount_image();
}

static int read_image(void) {
    int err = mount_image(0);
    if (err) {
        return err;
    }
    // Stock leaves info.size untouched for a struct type it does not know (an
    // extent), so zero it first: the answer that matters is that the inode is
    // visible and the normal file is intact.
    struct lfs_info info;
    memset(&info, 0, sizeof(info));
    err = lfs_stat(&lfs, "hello", &info);
    if (err) {
        printf("hello: no such file (%d)\n", err);
        return err;
    }
    char back[8] = {0};
    lfs_file_t file;
    err = lfs_file_open(&lfs, &file, "hello", LFS_O_RDONLY);
    if (err) {
        return err;
    }
    lfs_ssize_t read = lfs_file_read(&lfs, &file, back, sizeof(back));
    lfs_file_close(&lfs, &file);
    if (read != 5 || memcmp(back, "hello", 5) != 0) {
        printf("hello: read back %d bytes, content %s\n", (int)read, back);
        return 2;
    }
    printf("normal file: size %u, content ok\n", (unsigned)info.size);

    memset(&info, 0, sizeof(info));
    err = lfs_stat(&lfs, "core.bin", &info);
    if (err) {
        printf("extent inode: not visible to this mount (%d)\n", err);
        return 2;
    }
    printf("extent inode: visible to stock as a file (size not understood: %u)\n",
           (unsigned)info.size);
    return unmount_image();
}

static int clobber_image(void) {
    int err = mount_image(0);
    if (err) {
        return err;
    }
    lfs_file_t file;
    err = lfs_file_open(&lfs, &file, "junk",
                        LFS_O_WRONLY | LFS_O_CREAT | LFS_O_TRUNC);
    if (err) {
        return err;
    }
    static uint8_t chunk[BLOCK_SIZE];
    memset(chunk, 0xa5, sizeof(chunk));
    int written = 0;
    for (int i = 0; i < 4 * BLOCK_COUNT; i++) {
        lfs_ssize_t n = lfs_file_write(&lfs, &file, chunk, sizeof(chunk));
        if (n < 0) {
            break;
        }
        written += (int)n;
    }
    lfs_file_close(&lfs, &file);
    printf("filled %d bytes of the free space\n", written);
    return unmount_image();
}

static int check_image(void) {
    int err = mount_image(0);
    if (err) {
        return err;
    }
#ifdef HAVE_EXTENTS
    lfs_ext_t ext;
    err = lfs_ext_info(&lfs, "core.bin", &ext);
    if (err) {
        printf("extent: %d\n", err);
        return 2;
    }
    static uint8_t data[EXTENT_SIZE];
    lfs_file_t file;
    err = lfs_file_open(&lfs, &file, "core.bin", LFS_O_RDONLY);
    if (err) {
        return err;
    }
    lfs_ssize_t read = lfs_file_read(&lfs, &file, data, ext.length);
    lfs_file_close(&lfs, &file);
    if (read != (lfs_ssize_t)ext.length) {
        printf("extent: read %d of %u bytes\n", (int)read, (unsigned)ext.length);
        return 2;
    }
    uint32_t crc = lfs_crc(0, data, ext.length);
    unmount_image();
    if (crc != ext.crc) {
        printf("extent CRC %08x, stored %08x: the payload was overwritten\n",
               (unsigned)crc, (unsigned)ext.crc);
        return 3;
    }
    printf("extent CRC %08x: intact\n", (unsigned)crc);
    return 0;
#else
    printf("ERROR: the create/check side is the fork; build it with -DHAVE_EXTENTS\n");
    return 1;
#endif
}

int main(int argc, char **argv) {
    if (argc != 3) {
        printf("usage: %s create|read|clobber|check <image>\n", argv[0]);
        return 1;
    }
    image_path = argv[2];
    if (strcmp(argv[1], "create") == 0) {
        return create_image();
    }
    if (strcmp(argv[1], "read") == 0) {
        return read_image();
    }
    if (strcmp(argv[1], "clobber") == 0) {
        return clobber_image();
    }
    if (strcmp(argv[1], "check") == 0) {
        return check_image();
    }
    printf("unknown mode %s\n", argv[1]);
    return 1;
}
