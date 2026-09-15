// Display class of the `usb` module: Pico_USB_Disp display adapters
// (DisplayLink USB display adapters) on ESP32 native USB OTG.
//
// ESP32-only. Single display use is expected (USB_DISP_MAX == 1 on ESP32)
// but the type supports handles generally.
//
// Pins are fixed on ESP32 (native USB OTG, GPIO19/20), so only the port
// number is needed. Resolution 0x0 means EDID automatic selection.

#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "usb_disp.h"

typedef struct _mp_obj_usb_display_t {
    mp_obj_base_t base;
    usb_disp_t *disp;
} mp_obj_usb_display_t;

const mp_obj_type_t mp_type_usb_display;

static bool s_usb_display_inited = false;

static mp_obj_usb_display_t *usb_display_get_self(mp_obj_t self_in) {
    mp_obj_usb_display_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->disp == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("display not added"));
    }
    return self;
}

// Display(port=0, width=0, height=0, ignore_edid=False)
static mp_obj_t usb_display_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    enum { ARG_port, ARG_width, ARG_height, ARG_ignore_edid };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_port, MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_width, MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_height, MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_ignore_edid, MP_ARG_BOOL, {.u_bool = false} },
    };
    mp_arg_val_t parsed[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, args, MP_ARRAY_SIZE(allowed_args), allowed_args, parsed);

    if (!s_usb_display_inited) {
        usb_disp_init();
        s_usb_display_inited = true;
    }

    // Upstream has no remove API and ESP32 allows a single display, so a
    // slot once added is taken forever. Reuse it: this makes REPL retries
    // after a boot-time timeout and repeated constructions work. The
    // original width/height config is kept; use set_mode() to change it.
    usb_disp_t *d;
    if (usb_disp_count() > 0) {
        d = usb_disp_at(0);
    } else {
        d = usb_disp_add(
            (uint8_t)parsed[ARG_port].u_int,
            0, 0,
            (uint16_t)parsed[ARG_width].u_int,
            (uint16_t)parsed[ARG_height].u_int,
            parsed[ARG_ignore_edid].u_bool);
    }
    if (d == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("usb_disp_add failed"));
    }

    mp_obj_usb_display_t *self = mp_obj_malloc(mp_obj_usb_display_t, type);
    self->disp = d;
    return MP_OBJ_FROM_PTR(self);
}

// start() - start the USB host for all registered ports (call once)
static mp_obj_t usb_display_start(mp_obj_t self_in) {
    (void)self_in;
    usb_disp_start();
    return mp_const_none;
}

// poll() - drive enumeration/mode setup; True on READY/disconnect/mode change
static mp_obj_t usb_display_poll(mp_obj_t self_in) {
    mp_obj_usb_display_t *self = usb_display_get_self(self_in);
    return mp_obj_new_bool(usb_disp_poll(self->disp));
}

static mp_obj_t usb_display_ready(mp_obj_t self_in) {
    mp_obj_usb_display_t *self = usb_display_get_self(self_in);
    return mp_obj_new_bool(usb_disp_ready(self->disp));
}

static mp_obj_t usb_display_width(mp_obj_t self_in) {
    mp_obj_usb_display_t *self = usb_display_get_self(self_in);
    return mp_obj_new_int(usb_disp_width(self->disp));
}

static mp_obj_t usb_display_height(mp_obj_t self_in) {
    mp_obj_usb_display_t *self = usb_display_get_self(self_in);
    return mp_obj_new_int(usb_disp_height(self->disp));
}

// update_565(x, y, w, h, buf) - queue an RGB565 rectangle; pixels are copied
// synchronously into the bulk ring, buf may be reused right after return.
static mp_obj_t usb_display_update_565(size_t n_args, const mp_obj_t *args) {
    mp_obj_usb_display_t *self = usb_display_get_self(args[0]);
    uint16_t x = (uint16_t)mp_obj_get_int(args[1]);
    uint16_t y = (uint16_t)mp_obj_get_int(args[2]);
    uint16_t w = (uint16_t)mp_obj_get_int(args[3]);
    uint16_t h = (uint16_t)mp_obj_get_int(args[4]);
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[5], &bufinfo, MP_BUFFER_READ);
    if (bufinfo.len < (size_t)w * h * 2) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer too small"));
    }
    bool ok = usb_disp_update_565(self->disp, x, y, w, h, (const uint16_t *)bufinfo.buf, w);
    return mp_obj_new_bool(ok);
}

// fill(x, y, w, h, color) - solid RGB565 fill
static mp_obj_t usb_display_fill(size_t n_args, const mp_obj_t *args) {
    mp_obj_usb_display_t *self = usb_display_get_self(args[0]);
    bool ok = usb_disp_fill(self->disp,
        (uint16_t)mp_obj_get_int(args[1]),
        (uint16_t)mp_obj_get_int(args[2]),
        (uint16_t)mp_obj_get_int(args[3]),
        (uint16_t)mp_obj_get_int(args[4]),
        (uint16_t)mp_obj_get_int(args[5]));
    (void)n_args;
    return mp_obj_new_bool(ok);
}

// flush(timeout_ms=100) - submit queued data and wait for completion
static mp_obj_t usb_display_flush(size_t n_args, const mp_obj_t *args) {
    mp_obj_usb_display_t *self = usb_display_get_self(args[0]);
    uint32_t timeout = 100;
    if (n_args > 1) {
        timeout = (uint32_t)mp_obj_get_int(args[1]);
    }
    return mp_obj_new_bool(usb_disp_flush(self->disp, timeout));
}

// set_mode(width, height) - change resolution at 60Hz (redraw required)
static mp_obj_t usb_display_set_mode(mp_obj_t self_in, mp_obj_t w_in, mp_obj_t h_in) {
    mp_obj_usb_display_t *self = usb_display_get_self(self_in);
    bool ok = usb_disp_set_mode(self->disp, (uint16_t)mp_obj_get_int(w_in), (uint16_t)mp_obj_get_int(h_in));
    return mp_obj_new_bool(ok);
}

static mp_obj_t usb_display_chip_name(mp_obj_t self_in) {
    mp_obj_usb_display_t *self = usb_display_get_self(self_in);
    const char *name = usb_disp_chip_name(self->disp);
    if (name == NULL) {
        return mp_const_none;
    }
    return mp_obj_new_str(name, strlen(name));
}

// force_reenum() - root-port power cycle: virtual replug of the whole USB
// subtree. Recovers wedged adapters and stack-disabled ports, and
// re-triggers enumeration (e.g. after the adapter finished booting).
static mp_obj_t usb_display_force_reenum(mp_obj_t self_in) {
    mp_obj_usb_display_t *self = usb_display_get_self(self_in);
    usb_disp_force_reenum(self->disp);
    return mp_const_none;
}

static MP_DEFINE_CONST_FUN_OBJ_1(usb_display_start_obj, usb_display_start);
static MP_DEFINE_CONST_FUN_OBJ_1(usb_display_poll_obj, usb_display_poll);
static MP_DEFINE_CONST_FUN_OBJ_1(usb_display_ready_obj, usb_display_ready);
static MP_DEFINE_CONST_FUN_OBJ_1(usb_display_width_obj, usb_display_width);
static MP_DEFINE_CONST_FUN_OBJ_1(usb_display_height_obj, usb_display_height);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(usb_display_update_565_obj, 6, 6, usb_display_update_565);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(usb_display_fill_obj, 6, 6, usb_display_fill);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(usb_display_flush_obj, 1, 2, usb_display_flush);
static MP_DEFINE_CONST_FUN_OBJ_3(usb_display_set_mode_obj, usb_display_set_mode);
static MP_DEFINE_CONST_FUN_OBJ_1(usb_display_chip_name_obj, usb_display_chip_name);

static MP_DEFINE_CONST_FUN_OBJ_1(usb_display_force_reenum_obj, usb_display_force_reenum);

static const mp_rom_map_elem_t usb_display_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&usb_display_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_poll), MP_ROM_PTR(&usb_display_poll_obj) },
    { MP_ROM_QSTR(MP_QSTR_ready), MP_ROM_PTR(&usb_display_ready_obj) },
    { MP_ROM_QSTR(MP_QSTR_width), MP_ROM_PTR(&usb_display_width_obj) },
    { MP_ROM_QSTR(MP_QSTR_height), MP_ROM_PTR(&usb_display_height_obj) },
    { MP_ROM_QSTR(MP_QSTR_update_565), MP_ROM_PTR(&usb_display_update_565_obj) },
    { MP_ROM_QSTR(MP_QSTR_fill), MP_ROM_PTR(&usb_display_fill_obj) },
    { MP_ROM_QSTR(MP_QSTR_flush), MP_ROM_PTR(&usb_display_flush_obj) },
    { MP_ROM_QSTR(MP_QSTR_force_reenum), MP_ROM_PTR(&usb_display_force_reenum_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_mode), MP_ROM_PTR(&usb_display_set_mode_obj) },
    { MP_ROM_QSTR(MP_QSTR_chip_name), MP_ROM_PTR(&usb_display_chip_name_obj) },
};

static MP_DEFINE_CONST_DICT(usb_display_locals_dict, usb_display_locals_table);

MP_DEFINE_CONST_OBJ_TYPE(
    mp_type_usb_display,
    MP_QSTR_Display,
    MP_TYPE_FLAG_NONE,
    make_new, usb_display_make_new,
    locals_dict, &usb_display_locals_dict
);
