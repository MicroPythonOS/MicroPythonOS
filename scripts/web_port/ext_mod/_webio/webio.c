// _webio — browser GPIO-ish bridge for the MicroPythonOS WebAssembly build.
//
// Emulates badge peripherals in the browser page (see web/shell.html):
//
// Direction Python -> host (NeoPixel LEDs):
//   The staged `neopixel` shim calls leds_write(bytes) with packed RGB
//   triples; the bytes are handed to Module.__webio.onLeds (a JS callback the
//   page installs) as a Uint8Array so the page can paint LED dots.
//
// Direction host -> Python (buttons + joystick):
//   The page keeps a bitmask in Module.__webio.buttons whose bit positions
//   match the Fri3d 2026 expander `digital` tuple indices:
//     bit 1 joy_right, bit 2 joy_left, bit 3 joy_down, bit 4 joy_up,
//     bit 5 button_menu, bit 6 button_b, bit 7 button_a,
//     bit 8 button_y, bit 9 button_x
//   and analog joystick axes in Module.__webio.joy_x / joy_y (0..4095,
//   centered at 2048). Python polls with buttons() / joystick().
//
// This file is only compiled for the Emscripten/web target (guarded by
// __EMSCRIPTEN__ and gated to MPOS_WEB=1 in micropython.mk); on every other
// port it compiles to nothing.

#include <stdlib.h>

#include "py/runtime.h"
#include "py/obj.h"

#if defined(__EMSCRIPTEN__)

#include <emscripten.h>

EM_JS(void, webio_js_init, (void), {
    var H = Module.__webio || (Module.__webio = {});
    if (typeof H.buttons !== "number") { H.buttons = 0; }
    if (typeof H.joy_x !== "number") { H.joy_x = 2048; }
    if (typeof H.joy_y !== "number") { H.joy_y = 2048; }
    if (!H.onLeds) { H.onLeds = null; }
});

EM_JS(void, webio_js_leds, (const char *buf, int len), {
    var H = Module.__webio; if (!H || typeof H.onLeds !== "function") return;
    // Copy out of the wasm heap before handing to JS (the heap may move/grow).
    try { H.onLeds(HEAPU8.slice(buf, buf + len)); } catch (e) {}
});

EM_JS(int, webio_js_buttons, (void), {
    var H = Module.__webio; if (!H) return 0;
    return H.buttons | 0;
});

EM_JS(int, webio_js_joy, (int axis), {
    var H = Module.__webio; if (!H) return 2048;
    return (axis ? H.joy_y : H.joy_x) | 0;
});

// ---------------------------------------------------------------------------
// MicroPython bindings
// ---------------------------------------------------------------------------

// init() -> None  (ensure Module.__webio.{buttons,joy_x,joy_y,onLeds} exist)
static mp_obj_t webio_init(void) {
    webio_js_init();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(webio_init_obj, webio_init);

// leds_write(data:bytes) -> None  (packed RGB triples, one per LED)
static mp_obj_t webio_leds_write(mp_obj_t data_in) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_in, &bufinfo, MP_BUFFER_READ);
    if (bufinfo.len > 0) {
        webio_js_leds((const char *)bufinfo.buf, (int)bufinfo.len);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webio_leds_write_obj, webio_leds_write);

// buttons() -> int  (bitmask; bit positions match expander digital indices)
static mp_obj_t webio_buttons(void) {
    return mp_obj_new_int(webio_js_buttons());
}
static MP_DEFINE_CONST_FUN_OBJ_0(webio_buttons_obj, webio_buttons);

// joystick() -> (x, y)  (analog axes, 0..4095, 2048 = centered)
static mp_obj_t webio_joystick(void) {
    mp_obj_t items[2] = {
        mp_obj_new_int(webio_js_joy(0)),
        mp_obj_new_int(webio_js_joy(1)),
    };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(webio_joystick_obj, webio_joystick);

static const mp_rom_map_elem_t webio_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__webio) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&webio_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_leds_write), MP_ROM_PTR(&webio_leds_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_buttons), MP_ROM_PTR(&webio_buttons_obj) },
    { MP_ROM_QSTR(MP_QSTR_joystick), MP_ROM_PTR(&webio_joystick_obj) },
};
static MP_DEFINE_CONST_DICT(webio_module_globals, webio_module_globals_table);

const mp_obj_module_t webio_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&webio_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__webio, webio_user_cmodule);

#endif // __EMSCRIPTEN__
