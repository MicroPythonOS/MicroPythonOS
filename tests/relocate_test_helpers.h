// Helpers for tests/test_relocate.toml.
//
// Injected with --include, replacing littlefs's default header include, so it
// must pull in the runner header itself.
#ifndef RELOCATE_TEST_HELPERS_H
#define RELOCATE_TEST_HELPERS_H

#include "runners/test_runner.h"

// Every generated file gets this header, including the library copies
// (lfs.c, lfs_util.c), which use none of the helpers.
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#endif

// Deterministic fixture data.
static uint32_t rel_crc32(const void *p, size_t n) {
    const uint8_t *d = p;
    uint32_t c = 0xffffffff;
    for (size_t i = 0; i < n; i++) {
        c ^= d[i];
        for (int k = 0; k < 8; k++) {
            c = (c >> 1) ^ (0xEDB88320u & ((uint32_t)-(int32_t)(c & 1)));
        }
    }
    return ~c;
}

static void rel_fill(uint8_t *buf, int size, int seed) {
    uint32_t s = (uint32_t)(seed+1) * 2654435761u;
    for (int i = 0; i < size; i++) {
        s = s * 1103515245u + 12345u;
        buf[i] = (uint8_t)(s >> 16);
    }
}

// Writes `size` deterministic bytes; returns 0 or a negative error.
static int rel_write(lfs_t *lfs, const char *path, int size, int seed) {
    static uint8_t buf[700000];
    if (size > (int)sizeof(buf)) {
        return LFS_ERR_INVAL;
    }
    rel_fill(buf, size, seed);
    lfs_file_t file;
    int err = lfs_file_open(lfs, &file, path,
            LFS_O_WRONLY | LFS_O_CREAT | LFS_O_TRUNC);
    if (err) {
        return err;
    }
    lfs_ssize_t n = lfs_file_write(lfs, &file, buf, size);
    int cerr = lfs_file_close(lfs, &file);
    if (n != size) {
        return n < 0 ? (int)n : LFS_ERR_IO;
    }
    return cerr;
}

// Reads the file back and compares: 0 matches, 1 wrong bytes, <0 error.
static int rel_check(lfs_t *lfs, const char *path, int size, int seed) {
    static uint8_t want[700000];
    static uint8_t got[700000];
    if (size > (int)sizeof(want)) {
        return LFS_ERR_INVAL;
    }
    rel_fill(want, size, seed);
    lfs_file_t file;
    int err = lfs_file_open(lfs, &file, path, LFS_O_RDONLY);
    if (err) {
        return err;
    }
    lfs_ssize_t n = lfs_file_read(lfs, &file, got, size);
    lfs_file_close(lfs, &file);
    if (n != size) {
        return n < 0 ? (int)n : LFS_ERR_INVAL;
    }
    return memcmp(want, got, size) == 0 ? 0 : 1;
}

static int rel_pair_of(lfs_t *lfs, const char *path, lfs_block_t out[2]) {
    lfs_dir_t dir;
    int err = lfs_dir_open(lfs, &dir, path);
    if (err) {
        return err;
    }
    out[0] = dir.m.pair[0];
    out[1] = dir.m.pair[1];
    lfs_dir_close(lfs, &dir);
    return 0;
}

static int rel_same_pair(const lfs_block_t a[2], const lfs_block_t b[2]) {
    return (a[0] == b[0] && a[1] == b[1]) || (a[0] == b[1] && a[1] == b[0]);
}

// True when `after` uses a block that was not in `before` (a relocation).
static int rel_new_block(const lfs_block_t before[2], const lfs_block_t after[2]) {
    return (after[0] != before[0] && after[0] != before[1])
        || (after[1] != before[0] && after[1] != before[1]);
}

static int rel_bit(const uint8_t *map, int block) {
    return (map[block / 8] >> (block % 8)) & 1;
}

static int rel_largest(const uint8_t *used, int block_count, int align) {
    int best = 0;
    for (int i = 0; i < block_count; i += align) {
        if (rel_bit(used, i)) {
            continue;
        }
        int run = 0;
        while (i+run < block_count && !rel_bit(used, i+run)) {
            run++;
        }
        if (run > best) {
            best = run;
        }
    }
    return best;
}

// Walk the tree from the root and count directories and duplicate pairs.
// A pair reachable twice is the corruption a buggy relocation leaves behind.
static int rel_walk(lfs_t *lfs, const char *path, int depth,
        uint8_t *seen, int block_count, int *dirs, int *dups) {
    if (depth > 8) {
        return -1;
    }
    lfs_dir_t dir;
    int err = lfs_dir_open(lfs, &dir, path);
    if (err) {
        return err;
    }
    for (int i = 0; i < 2; i++) {
        lfs_block_t b = dir.m.pair[i];
        if (b < (lfs_block_t)block_count) {
            if (seen[b]) {
                *dups += 1;
            }
            seen[b] = 1;
        }
    }
    *dirs += 1;

    struct lfs_info info;
    while ((err = lfs_dir_read(lfs, &dir, &info)) > 0) {
        if (info.type != LFS_TYPE_DIR) {
            continue;
        }
        if (strcmp(info.name, ".") == 0 || strcmp(info.name, "..") == 0) {
            continue;
        }
        char child[LFS_NAME_MAX+2];
        int plen = strlen(path);
        int nlen = strlen(info.name);
        bool slash = strcmp(path, "/") != 0;
        if (plen + (slash ? 1 : 0) + nlen + 1 > (int)sizeof(child)) {
            err = LFS_ERR_NAMETOOLONG;
            break;
        }
        memcpy(child, path, plen);
        int o = plen;
        if (slash) {
            child[o++] = '/';
        }
        memcpy(child + o, info.name, nlen);
        child[o + nlen] = 0;
        int res = rel_walk(lfs, child, depth+1, seen, block_count, dirs, dups);
        if (res) {
            err = res;
            break;
        }
    }
    lfs_dir_close(lfs, &dir);
    return err < 0 ? err : 0;
}

// Collects directory pairs for the split-directory case.
struct rel_pair_list {
    lfs_block_t pair[64][2];
    bool is_tail[64];
    int count;
};

static int rel_pairs_cb(void *data, const lfs_block_t pair[2], bool tail) {
    struct rel_pair_list *list = data;
    if (list->count < 64) {
        list->pair[list->count][0] = pair[0];
        list->pair[list->count][1] = pair[1];
        list->is_tail[list->count] = tail;
        list->count++;
    }
    return 0;
}

// Injected prog/erase failures, so a test can force the bad-block relocation
// path deterministically (see the parent-chain case).
static lfs_block_t rel_bad_prog = ((lfs_block_t)-1);
static lfs_block_t rel_bad_erase = ((lfs_block_t)-1);
static int (*rel_orig_prog)(const struct lfs_config *c, lfs_block_t block,
        lfs_off_t off, const void *buffer, lfs_size_t size);
static int (*rel_orig_erase)(const struct lfs_config *c, lfs_block_t block);

static int rel_prog_cb(const struct lfs_config *c, lfs_block_t block,
        lfs_off_t off, const void *buffer, lfs_size_t size) {
    if (block == rel_bad_prog) {
        return LFS_ERR_CORRUPT;
    }
    return rel_orig_prog(c, block, off, buffer, size);
}

static int rel_erase_cb(const struct lfs_config *c, lfs_block_t block) {
    if (block == rel_bad_erase) {
        return LFS_ERR_CORRUPT;
    }
    return rel_orig_erase(c, block);
}

static void rel_install_bad_blocks(struct lfs_config *cfg) {
    rel_orig_prog = cfg->prog;
    rel_orig_erase = cfg->erase;
    cfg->prog = rel_prog_cb;
    cfg->erase = rel_erase_cb;
}

static void rel_remove_bad_blocks(struct lfs_config *cfg) {
    cfg->prog = rel_orig_prog;
    cfg->erase = rel_orig_erase;
    rel_bad_prog = ((lfs_block_t)-1);
    rel_bad_erase = ((lfs_block_t)-1);
}

#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

#endif
