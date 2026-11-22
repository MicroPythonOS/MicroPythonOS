// lfs2e - littlefs2e extent-file support for MicroPythonOS.
//
// An extent file is an immutable, contiguous run of raw blocks. This module
// is the thin bridge between the Python policy layer (mpos.extent) and the
// littlefs2e API in lib/littlefs/lfs2.c. The actual filesystem mounted at
// "/" is littlefs2; the extent API needs its lfs2_t, which the VFS does not
// expose to Python.

#include "py/runtime.h"
#include "py/obj.h"
#include "py/objlist.h"
#include "py/objarray.h"
#include "extmod/vfs_lfs.h"

#if MICROPY_VFS_LFS2

static lfs2_t *lfs2e_get(void) {
    lfs2_t *lfs = mp_vfs_lfs2_root_lfs2();
    if (lfs == NULL) {
        mp_raise_msg(&mp_type_OSError,
                MP_ERROR_TEXT("the root filesystem is not littlefs2"));
    }
    return lfs;
}

static void lfs2e_check(int err) {
    if (err < 0) {
        mp_raise_OSError(-err);
    }
}

static mp_obj_t lfs2e_geometry(void) {
    lfs2_t *lfs = lfs2e_get();
    mp_obj_t tuple[3] = {
        mp_obj_new_int_from_uint(lfs->cfg->block_size),
        mp_obj_new_int_from_uint(lfs->block_count),
        mp_obj_new_int_from_uint(lfs2_fs_disk_version(lfs)),
    };
    return mp_obj_new_tuple(3, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_0(lfs2e_geometry_obj, lfs2e_geometry);

static mp_obj_t lfs2e_reserve(size_t n_args, const mp_obj_t *args) {
    lfs2_t *lfs = lfs2e_get();
    mp_uint_t length = mp_obj_get_int_truncated(args[0]);
    mp_uint_t align = (n_args > 1) ? mp_obj_get_int_truncated(args[1]) : 1;
    lfs2_ext_t ext;
    int err = lfs2_ext_reserve(lfs, length, align, &ext);
    lfs2e_check(err);
    mp_obj_t tuple[2] = {
        mp_obj_new_int_from_uint(ext.head),
        mp_obj_new_int_from_uint(ext.count),
    };
    return mp_obj_new_tuple(2, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(lfs2e_reserve_obj, 1, 2, lfs2e_reserve);

static mp_obj_t lfs2e_defrag(size_t n_args, const mp_obj_t *args) {
    lfs2_t *lfs = lfs2e_get();
    mp_uint_t length = mp_obj_get_int_truncated(args[0]);
    mp_uint_t align = (n_args > 1) ? mp_obj_get_int_truncated(args[1]) : 1;
    mp_uint_t budget = (n_args > 2) ? mp_obj_get_int_truncated(args[2]) : 0;
    lfs2_ext_t ext;
    int err = lfs2_ext_defrag(lfs, length, align, budget, &ext);
    lfs2e_check(err);
    mp_obj_t tuple[2] = {
        mp_obj_new_int_from_uint(ext.head),
        mp_obj_new_int_from_uint(ext.count),
    };
    return mp_obj_new_tuple(2, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(lfs2e_defrag_obj, 1, 3, lfs2e_defrag);

// The step driver: begin() reserves nothing on its own; step() returns
// (running, phase, percent) until it returns running == 0, at which point the
// run is reserved; result() reports it. abort() drops a stale run (a mount
// does the same).
static mp_obj_t lfs2e_defrag_begin(size_t n_args, const mp_obj_t *args) {
    lfs2_t *lfs = lfs2e_get();
    mp_uint_t length = mp_obj_get_int_truncated(args[0]);
    mp_uint_t align = (n_args > 1) ? mp_obj_get_int_truncated(args[1]) : 1;
    mp_uint_t budget = (n_args > 2) ? mp_obj_get_int_truncated(args[2]) : 0;
    lfs2e_check(lfs2_ext_defrag_begin(lfs, length, align, budget));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(lfs2e_defrag_begin_obj, 1, 3,
        lfs2e_defrag_begin);

static mp_obj_t lfs2e_defrag_step(void) {
    lfs2_t *lfs = lfs2e_get();
    uint8_t phase = 0;
    uint8_t percent = 0;
    int res = lfs2_ext_defrag_step(lfs, &phase, &percent);
    lfs2e_check(res);
    mp_obj_t tuple[3] = {
        mp_obj_new_int(res),
        mp_obj_new_int(phase),
        mp_obj_new_int(percent),
    };
    return mp_obj_new_tuple(3, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_0(lfs2e_defrag_step_obj, lfs2e_defrag_step);

static mp_obj_t lfs2e_defrag_result(void) {
    lfs2_t *lfs = lfs2e_get();
    lfs2_ext_t ext;
    lfs2e_check(lfs2_ext_defrag_result(lfs, &ext));
    mp_obj_t tuple[2] = {
        mp_obj_new_int_from_uint(ext.head),
        mp_obj_new_int_from_uint(ext.count),
    };
    return mp_obj_new_tuple(2, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_0(lfs2e_defrag_result_obj, lfs2e_defrag_result);

static mp_obj_t lfs2e_defrag_abort(void) {
    lfs2_t *lfs = lfs2e_get();
    lfs2_ext_defrag_abort(lfs);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(lfs2e_defrag_abort_obj, lfs2e_defrag_abort);

static mp_obj_t lfs2e_write(mp_obj_t offset_in, mp_obj_t buf_in) {
    lfs2_t *lfs = lfs2e_get();
    mp_uint_t offset = mp_obj_get_int_truncated(offset_in);
    mp_buffer_info_t buf;
    mp_get_buffer_raise(buf_in, &buf, MP_BUFFER_READ);
    int err = lfs2_ext_write(lfs, offset, buf.buf, buf.len);
    lfs2e_check(err);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(lfs2e_write_obj, lfs2e_write);

static mp_obj_t lfs2e_commit(size_t n_args, const mp_obj_t *args) {
    lfs2_t *lfs = lfs2e_get();
    const char *path = mp_obj_str_get_str(args[0]);
    mp_uint_t crc = (n_args > 1) ? mp_obj_get_int_truncated(args[1]) : 0;
    // Capture the descriptor for the return value; commit clears it.
    lfs2_block_t head = lfs->ext_head;
    lfs2_size_t length = lfs->ext_length;
    int err = lfs2_ext_commit(lfs, path, crc);
    lfs2e_check(err);
    mp_obj_t tuple[2] = {
        mp_obj_new_int_from_uint(head * lfs->cfg->block_size),
        mp_obj_new_int_from_uint(length),
    };
    return mp_obj_new_tuple(2, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(lfs2e_commit_obj, 1, 2, lfs2e_commit);

static mp_obj_t lfs2e_abort(void) {
    lfs2_t *lfs = lfs2e_get();
    lfs2_ext_abort(lfs);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(lfs2e_abort_obj, lfs2e_abort);

static mp_obj_t lfs2e_info(mp_obj_t path_in) {
    lfs2_t *lfs = lfs2e_get();
    const char *path = mp_obj_str_get_str(path_in);
    lfs2_ext_t ext;
    int err = lfs2_ext_info(lfs, path, &ext);
    if (err == LFS2_ERR_NOENT || err == LFS2_ERR_ISDIR) {
        return mp_const_none;
    }
    lfs2e_check(err);
    mp_obj_t tuple[3] = {
        mp_obj_new_int_from_uint(ext.head * lfs->cfg->block_size),
        mp_obj_new_int_from_uint(ext.length),
        mp_obj_new_int_from_uint(ext.crc),
    };
    return mp_obj_new_tuple(3, tuple);
}
static MP_DEFINE_CONST_FUN_OBJ_1(lfs2e_info_obj, lfs2e_info);

static mp_obj_t lfs2e_used_map(void) {
    lfs2_t *lfs = lfs2e_get();
    lfs2_size_t size = (lfs->block_count + 7) / 8;
    uint8_t *map = m_new(uint8_t, size);
    int err = lfs2_ext_block_maps(lfs, map, size, NULL, 0);
    if (err) {
        m_del(uint8_t, map, size);
        lfs2e_check(err);
    }
    mp_obj_t res = mp_obj_new_bytearray(size, map);
    m_del(uint8_t, map, size);
    return res;
}
static MP_DEFINE_CONST_FUN_OBJ_0(lfs2e_used_map_obj, lfs2e_used_map);

static mp_obj_t lfs2e_meta_map(void) {
    lfs2_t *lfs = lfs2e_get();
    lfs2_size_t size = (lfs->block_count + 7) / 8;
    uint8_t *map = m_new(uint8_t, size);
    int err = lfs2_ext_block_maps(lfs, NULL, 0, map, size);
    if (err) {
        m_del(uint8_t, map, size);
        lfs2e_check(err);
    }
    mp_obj_t res = mp_obj_new_bytearray(size, map);
    m_del(uint8_t, map, size);
    return res;
}
static MP_DEFINE_CONST_FUN_OBJ_0(lfs2e_meta_map_obj, lfs2e_meta_map);

static int lfs2e_blocks_cb(void *data, lfs2_block_t block) {
    mp_obj_list_append(MP_OBJ_FROM_PTR(data),
            mp_obj_new_int_from_uint(block));
    return 0;
}

static mp_obj_t lfs2e_file_blocks(mp_obj_t path_in) {
    lfs2_t *lfs = lfs2e_get();
    const char *path = mp_obj_str_get_str(path_in);
    mp_obj_t list = mp_obj_new_list(0, NULL);
    int err = lfs2_ext_file_blocks(lfs, path, lfs2e_blocks_cb, MP_OBJ_TO_PTR(list));
    lfs2e_check(err);
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_1(lfs2e_file_blocks_obj, lfs2e_file_blocks);

static mp_obj_t lfs2e_largest_run(size_t n_args, const mp_obj_t *args) {
    lfs2_t *lfs = lfs2e_get();
    mp_uint_t align = (n_args > 0) ? mp_obj_get_int_truncated(args[0]) : 1;
    return mp_obj_new_int_from_uint(lfs2_ext_largest_run(lfs, align));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(lfs2e_largest_run_obj, 0, 1,
        lfs2e_largest_run);

static mp_obj_t lfs2e_exclude(mp_obj_t head_in, mp_obj_t count_in) {
    lfs2_t *lfs = lfs2e_get();
    mp_uint_t head = mp_obj_get_int_truncated(head_in);
    mp_uint_t count = mp_obj_get_int_truncated(count_in);
    int err = lfs2_ext_exclude(lfs, head, count);
    lfs2e_check(err);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(lfs2e_exclude_obj, lfs2e_exclude);

static mp_obj_t lfs2e_clear_exclude(void) {
    lfs2_t *lfs = lfs2e_get();
    lfs2_ext_clear_exclude(lfs);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(lfs2e_clear_exclude_obj, lfs2e_clear_exclude);

static const mp_rom_map_elem_t lfs2e_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_lfs2e) },
    { MP_ROM_QSTR(MP_QSTR_geometry), MP_ROM_PTR(&lfs2e_geometry_obj) },
    { MP_ROM_QSTR(MP_QSTR_reserve), MP_ROM_PTR(&lfs2e_reserve_obj) },
    { MP_ROM_QSTR(MP_QSTR_defrag), MP_ROM_PTR(&lfs2e_defrag_obj) },
    { MP_ROM_QSTR(MP_QSTR_defrag_begin), MP_ROM_PTR(&lfs2e_defrag_begin_obj) },
    { MP_ROM_QSTR(MP_QSTR_defrag_step), MP_ROM_PTR(&lfs2e_defrag_step_obj) },
    { MP_ROM_QSTR(MP_QSTR_defrag_result), MP_ROM_PTR(&lfs2e_defrag_result_obj) },
    { MP_ROM_QSTR(MP_QSTR_defrag_abort), MP_ROM_PTR(&lfs2e_defrag_abort_obj) },
    { MP_ROM_QSTR(MP_QSTR_write), MP_ROM_PTR(&lfs2e_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_commit), MP_ROM_PTR(&lfs2e_commit_obj) },
    { MP_ROM_QSTR(MP_QSTR_abort), MP_ROM_PTR(&lfs2e_abort_obj) },
    { MP_ROM_QSTR(MP_QSTR_info), MP_ROM_PTR(&lfs2e_info_obj) },
    { MP_ROM_QSTR(MP_QSTR_used_map), MP_ROM_PTR(&lfs2e_used_map_obj) },
    { MP_ROM_QSTR(MP_QSTR_meta_map), MP_ROM_PTR(&lfs2e_meta_map_obj) },
    { MP_ROM_QSTR(MP_QSTR_file_blocks), MP_ROM_PTR(&lfs2e_file_blocks_obj) },
    { MP_ROM_QSTR(MP_QSTR_largest_run), MP_ROM_PTR(&lfs2e_largest_run_obj) },
    { MP_ROM_QSTR(MP_QSTR_exclude), MP_ROM_PTR(&lfs2e_exclude_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear_exclude), MP_ROM_PTR(&lfs2e_clear_exclude_obj) },
};
static MP_DEFINE_CONST_DICT(lfs2e_module_globals, lfs2e_module_globals_table);

const mp_obj_module_t lfs2e_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&lfs2e_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_lfs2e, lfs2e_module);

#endif // MICROPY_VFS_LFS2
