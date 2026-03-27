/**
 * MicroPython bindings for the esp32-component-rvswd RVSWD programmer.
 * Exposes an RVSWD class for programming WCH CH32 microcontrollers from Python.
 *
 * Usage:
 *   import rvswd
 *   prog = rvswd.RVSWD(swdio=39, swclk=42)
 *
 *   # Read chip identity
 *   vendor = prog.read_vendor_bytes()  # returns tuple of 4 uint32 values
 *
 *   # Program a CH32x03x chip (e.g. CH32X035)
 *   with open('firmware.bin', 'rb') as f:
 *       fw = f.read()
 *   prog.x03x_program(fw, lambda msg, pct: print(f"{msg}: {pct}%"))
 *
 *   # Program a CH32V20x chip (e.g. CH32V203)
 *   prog.halt()
 *   prog.v20x_unlock_flash()
 *   prog.v20x_write_flash(0x08000000, fw, lambda msg, pct: print(f"{msg}: {pct}%"))
 *   prog.v20x_lock_flash()
 *   prog.reset_and_run()
 */

#include "py/obj.h"
#include "py/runtime.h"
#include "py/mphal.h"
#include <string.h>
#include "rvswd.h"
#include "rvswd_ch32.h"
#include "rvswd_ch32v20x.h"
#include "rvswd_ch32x03x.h"

// ---------------------------------------------------------------------------
// Object type
// ---------------------------------------------------------------------------

typedef struct {
    mp_obj_base_t base;
    rvswd_handle_t handle;
} rvswd_obj_t;

static const mp_obj_type_t rvswd_type;  // forward declaration

// ---------------------------------------------------------------------------
// Callback bridge
// Single-threaded MicroPython GIL makes a global safe here;
// these flash functions are blocking and never re-entrant.
// ---------------------------------------------------------------------------

static mp_obj_t g_status_callback = MP_OBJ_NULL;

static void c_status_callback(char const *msg, uint8_t progress) {
    if (g_status_callback != MP_OBJ_NULL && g_status_callback != mp_const_none) {
        mp_obj_t call_args[2] = {
            mp_obj_new_str(msg, strlen(msg)),
            MP_OBJ_NEW_SMALL_INT(progress),
        };
        mp_call_function_n_kw(g_status_callback, 2, 0, call_args);
    }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

static void raise_rvswd_result(rvswd_result_t result) {
    switch (result) {
        case RVSWD_OK:           return;
        case RVSWD_FAIL:         mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("RVSWD operation failed")); break;
        case RVSWD_INVALID_ARGS: mp_raise_ValueError(MP_ERROR_TEXT("RVSWD invalid arguments")); break;
        case RVSWD_PARITY_ERROR: mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("RVSWD parity error")); break;
        default:                 mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("RVSWD error: %d"), (int)result); break;
    }
}

// ---------------------------------------------------------------------------
// Constructor: RVSWD(swdio, swclk)
// ---------------------------------------------------------------------------

static mp_obj_t rvswd_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    mp_arg_check_num(n_args, n_kw, 2, 2, false);
    rvswd_obj_t *self = mp_obj_malloc(rvswd_obj_t, type);
    self->handle.swdio = (gpio_num_t)mp_obj_get_int(args[0]);
    self->handle.swclk = (gpio_num_t)mp_obj_get_int(args[1]);
    rvswd_result_t result = rvswd_init(&self->handle);
    if (result != RVSWD_OK) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("rvswd_init failed: %d"), (int)result);
    }
    return MP_OBJ_FROM_PTR(self);
}

// ---------------------------------------------------------------------------
// Low-level RVSWD protocol
// ---------------------------------------------------------------------------

static mp_obj_t mprvswd_reset(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    raise_rvswd_result(rvswd_reset(&self->handle));
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_reset_obj, mprvswd_reset);

static mp_obj_t mprvswd_write_reg(mp_obj_t self_in, mp_obj_t reg_in, mp_obj_t val_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    uint8_t reg = (uint8_t)mp_obj_get_int(reg_in);
    uint32_t val = (uint32_t)mp_obj_get_int(val_in);
    raise_rvswd_result(rvswd_write(&self->handle, reg, val));
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_3(rvswd_write_reg_obj, mprvswd_write_reg);

static mp_obj_t mprvswd_read_reg(mp_obj_t self_in, mp_obj_t reg_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    uint8_t reg = (uint8_t)mp_obj_get_int(reg_in);
    uint32_t val = 0;
    raise_rvswd_result(rvswd_read(&self->handle, reg, &val));
    return mp_obj_new_int_from_uint(val);
}
MP_DEFINE_CONST_FUN_OBJ_2(rvswd_read_reg_obj, mprvswd_read_reg);

// ---------------------------------------------------------------------------
// CH32 generic debug operations
// ---------------------------------------------------------------------------

static mp_obj_t mprvswd_halt(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    raise_rvswd_result(ch32_halt_microprocessor(&self->handle));
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_halt_obj, mprvswd_halt);

static mp_obj_t mprvswd_resume(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    raise_rvswd_result(ch32_resume_microprocessor(&self->handle));
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_resume_obj, mprvswd_resume);

static mp_obj_t mprvswd_reset_and_run(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    raise_rvswd_result(ch32_reset_microprocessor_and_run(&self->handle));
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_reset_and_run_obj, mprvswd_reset_and_run);

static mp_obj_t mprvswd_read_memory(mp_obj_t self_in, mp_obj_t addr_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    uint32_t addr = (uint32_t)mp_obj_get_int(addr_in);
    uint32_t val = 0;
    if (!ch32_read_memory_word(&self->handle, addr, &val)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32_read_memory_word failed"));
    }
    return mp_obj_new_int_from_uint(val);
}
MP_DEFINE_CONST_FUN_OBJ_2(rvswd_read_memory_obj, mprvswd_read_memory);

static mp_obj_t mprvswd_write_memory(mp_obj_t self_in, mp_obj_t addr_in, mp_obj_t val_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    uint32_t addr = (uint32_t)mp_obj_get_int(addr_in);
    uint32_t val = (uint32_t)mp_obj_get_int(val_in);
    if (!ch32_write_memory_word(&self->handle, addr, val)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32_write_memory_word failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_3(rvswd_write_memory_obj, mprvswd_write_memory);

// Returns a 4-tuple of uint32 vendor bytes for chip identification.
static mp_obj_t mprvswd_read_vendor_bytes(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    uint32_t vendor_bytes[4] = {0, 0, 0, 0};
    if (!ch32_read_vendor_bytes(&self->handle, vendor_bytes)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32_read_vendor_bytes failed"));
    }
    mp_obj_t tuple[4];
    for (int i = 0; i < 4; i++) {
        tuple[i] = mp_obj_new_int_from_uint(vendor_bytes[i]);
    }
    return mp_obj_new_tuple(4, tuple);
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_read_vendor_bytes_obj, mprvswd_read_vendor_bytes);

// ---------------------------------------------------------------------------
// CH32V20x flash operations
// ---------------------------------------------------------------------------

// v20x_program(firmware[, callback])
// High-level: halts, erases, writes, verifies and restarts the target.
static mp_obj_t mprvswd_v20x_program(size_t n_args, const mp_obj_t *args) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[1], &bufinfo, MP_BUFFER_READ);

    g_status_callback = (n_args > 2) ? args[2] : mp_const_none;
    ch32v20x_status_callback cb = (g_status_callback != mp_const_none) ? c_status_callback : NULL;
    bool ok = ch32v20x_program(&self->handle, bufinfo.buf, bufinfo.len, cb);
    g_status_callback = MP_OBJ_NULL;

    if (!ok) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32v20x_program failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rvswd_v20x_program_obj, 2, 3, mprvswd_v20x_program);

static mp_obj_t mprvswd_v20x_unlock_flash(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (!ch32v20x_unlock_flash(&self->handle)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32v20x_unlock_flash failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_v20x_unlock_flash_obj, mprvswd_v20x_unlock_flash);

static mp_obj_t mprvswd_v20x_lock_flash(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (!ch32v20x_lock_flash(&self->handle)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32v20x_lock_flash failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_v20x_lock_flash_obj, mprvswd_v20x_lock_flash);

// v20x_write_flash(addr, data[, callback])
// data: bytes-like object with firmware content
// callback: optional callable(msg: str, progress: int)
static mp_obj_t mprvswd_v20x_write_flash(size_t n_args, const mp_obj_t *args) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    uint32_t addr = (uint32_t)mp_obj_get_int(args[1]);
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[2], &bufinfo, MP_BUFFER_READ);

    g_status_callback = (n_args > 3) ? args[3] : mp_const_none;
    ch32v20x_status_callback cb = (g_status_callback != mp_const_none) ? c_status_callback : NULL;
    bool ok = ch32v20x_write_flash(&self->handle, addr, bufinfo.buf, bufinfo.len, cb);
    g_status_callback = MP_OBJ_NULL;

    if (!ok) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32v20x_write_flash failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rvswd_v20x_write_flash_obj, 3, 4, mprvswd_v20x_write_flash);

static mp_obj_t mprvswd_v20x_clear_ops(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (!ch32v20x_clear_running_operations(&self->handle)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32v20x_clear_running_operations failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_v20x_clear_ops_obj, mprvswd_v20x_clear_ops);

// ---------------------------------------------------------------------------
// CH32x03x flash operations
// ---------------------------------------------------------------------------

// x03x_program(firmware[, callback])
// High-level: halts, erases, writes, verifies and restarts the target.
static mp_obj_t mprvswd_x03x_program(size_t n_args, const mp_obj_t *args) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[1], &bufinfo, MP_BUFFER_READ);

    g_status_callback = (n_args > 2) ? args[2] : mp_const_none;
    ch32x03x_status_callback cb = (g_status_callback != mp_const_none) ? c_status_callback : NULL;
    bool ok = ch32x03x_program(&self->handle, bufinfo.buf, bufinfo.len, cb);
    g_status_callback = MP_OBJ_NULL;

    if (!ok) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32x03x_program failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rvswd_x03x_program_obj, 2, 3, mprvswd_x03x_program);

static mp_obj_t mprvswd_x03x_unlock_flash(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (!ch32x03x_unlock_flash(&self->handle)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32x03x_unlock_flash failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_x03x_unlock_flash_obj, mprvswd_x03x_unlock_flash);

static mp_obj_t mprvswd_x03x_lock_flash(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (!ch32x03x_lock_flash(&self->handle)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32x03x_lock_flash failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_x03x_lock_flash_obj, mprvswd_x03x_lock_flash);

// x03x_write_flash(addr, data[, callback])
static mp_obj_t mprvswd_x03x_write_flash(size_t n_args, const mp_obj_t *args) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    uint32_t addr = (uint32_t)mp_obj_get_int(args[1]);
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[2], &bufinfo, MP_BUFFER_READ);

    g_status_callback = (n_args > 3) ? args[3] : mp_const_none;
    ch32x03x_status_callback cb = (g_status_callback != mp_const_none) ? c_status_callback : NULL;
    bool ok = ch32x03x_write_flash(&self->handle, addr, bufinfo.buf, bufinfo.len, cb);
    g_status_callback = MP_OBJ_NULL;

    if (!ok) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32x03x_write_flash failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rvswd_x03x_write_flash_obj, 3, 4, mprvswd_x03x_write_flash);

static mp_obj_t mprvswd_x03x_clear_ops(mp_obj_t self_in) {
    rvswd_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (!ch32x03x_clear_running_operations(&self->handle)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("ch32x03x_clear_running_operations failed"));
    }
    return mp_const_none;
}
MP_DEFINE_CONST_FUN_OBJ_1(rvswd_x03x_clear_ops_obj, mprvswd_x03x_clear_ops);

// ---------------------------------------------------------------------------
// Type definition
// ---------------------------------------------------------------------------

static const mp_rom_map_elem_t rvswd_locals_dict_table[] = {
    // Low-level RVSWD protocol
    { MP_ROM_QSTR(MP_QSTR_reset),             MP_ROM_PTR(&rvswd_reset_obj) },
    { MP_ROM_QSTR(MP_QSTR_write_reg),         MP_ROM_PTR(&rvswd_write_reg_obj) },
    { MP_ROM_QSTR(MP_QSTR_read_reg),          MP_ROM_PTR(&rvswd_read_reg_obj) },
    // CH32 generic
    { MP_ROM_QSTR(MP_QSTR_halt),              MP_ROM_PTR(&rvswd_halt_obj) },
    { MP_ROM_QSTR(MP_QSTR_resume),            MP_ROM_PTR(&rvswd_resume_obj) },
    { MP_ROM_QSTR(MP_QSTR_reset_and_run),     MP_ROM_PTR(&rvswd_reset_and_run_obj) },
    { MP_ROM_QSTR(MP_QSTR_read_memory),       MP_ROM_PTR(&rvswd_read_memory_obj) },
    { MP_ROM_QSTR(MP_QSTR_write_memory),      MP_ROM_PTR(&rvswd_write_memory_obj) },
    { MP_ROM_QSTR(MP_QSTR_read_vendor_bytes), MP_ROM_PTR(&rvswd_read_vendor_bytes_obj) },
    // CH32V20x
    { MP_ROM_QSTR(MP_QSTR_v20x_program),      MP_ROM_PTR(&rvswd_v20x_program_obj) },
    { MP_ROM_QSTR(MP_QSTR_v20x_unlock_flash), MP_ROM_PTR(&rvswd_v20x_unlock_flash_obj) },
    { MP_ROM_QSTR(MP_QSTR_v20x_lock_flash),   MP_ROM_PTR(&rvswd_v20x_lock_flash_obj) },
    { MP_ROM_QSTR(MP_QSTR_v20x_write_flash),  MP_ROM_PTR(&rvswd_v20x_write_flash_obj) },
    { MP_ROM_QSTR(MP_QSTR_v20x_clear_ops),    MP_ROM_PTR(&rvswd_v20x_clear_ops_obj) },
    // CH32x03x
    { MP_ROM_QSTR(MP_QSTR_x03x_program),      MP_ROM_PTR(&rvswd_x03x_program_obj) },
    { MP_ROM_QSTR(MP_QSTR_x03x_unlock_flash), MP_ROM_PTR(&rvswd_x03x_unlock_flash_obj) },
    { MP_ROM_QSTR(MP_QSTR_x03x_lock_flash),   MP_ROM_PTR(&rvswd_x03x_lock_flash_obj) },
    { MP_ROM_QSTR(MP_QSTR_x03x_write_flash),  MP_ROM_PTR(&rvswd_x03x_write_flash_obj) },
    { MP_ROM_QSTR(MP_QSTR_x03x_clear_ops),    MP_ROM_PTR(&rvswd_x03x_clear_ops_obj) },
};
static MP_DEFINE_CONST_DICT(rvswd_locals_dict, rvswd_locals_dict_table);

static const mp_obj_type_t rvswd_type = {
    { &mp_type_type },
    .name = MP_QSTR_RVSWD,
    .make_new = rvswd_make_new,
    .locals_dict = (mp_obj_dict_t *)&rvswd_locals_dict,
};

// ---------------------------------------------------------------------------
// Module definition
// ---------------------------------------------------------------------------

static const mp_rom_map_elem_t rvswd_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__),     MP_ROM_QSTR(MP_QSTR_rvswd) },
    { MP_ROM_QSTR(MP_QSTR_RVSWD),        MP_ROM_PTR(&rvswd_type) },
    // rvswd_result_t constants
    { MP_ROM_QSTR(MP_QSTR_OK),           MP_ROM_INT(RVSWD_OK) },
    { MP_ROM_QSTR(MP_QSTR_FAIL),         MP_ROM_INT(RVSWD_FAIL) },
    { MP_ROM_QSTR(MP_QSTR_INVALID_ARGS), MP_ROM_INT(RVSWD_INVALID_ARGS) },
    { MP_ROM_QSTR(MP_QSTR_PARITY_ERROR), MP_ROM_INT(RVSWD_PARITY_ERROR) },
};
static MP_DEFINE_CONST_DICT(rvswd_module_globals, rvswd_module_globals_table);

const mp_obj_module_t rvswd_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&rvswd_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_rvswd, rvswd_user_cmodule);
