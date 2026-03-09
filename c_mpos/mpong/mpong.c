// Include the header file to get access to the MicroPython API
#include "py/dynruntime.h"

// Global BSS (non-static) state is required for native modules.
size_t g_line_y;
uint16_t *g_framebuffer;
size_t g_framebuffer_len;
size_t g_framebuffer_width;
size_t g_framebuffer_height;

// readfile(filename): return first 10 bytes of a file as bytes
static mp_obj_t readfile(mp_obj_t filename_obj) {
    mp_obj_t open_fun = mp_load_global(MP_QSTR_open);
    mp_obj_t open_args[2] = { filename_obj, mp_obj_new_str("rb", 2) };
    mp_obj_t file_obj = mp_call_function_n_kw(open_fun, 2, 0, open_args);

    mp_obj_t read_fun = mp_load_attr(file_obj, MP_QSTR_read);
    mp_obj_t read_args[1] = { mp_obj_new_int(10) };
    mp_obj_t data_obj = mp_call_function_n_kw(read_fun, 1, 0, read_args);

    mp_obj_t close_fun = mp_load_attr(file_obj, MP_QSTR_close);
    mp_obj_t close_args[1];
    mp_call_function_n_kw(close_fun, 0, 0, close_args);

    return data_obj;
}
static MP_DEFINE_CONST_FUN_OBJ_1(readfile_obj, readfile);

// init(framebuffer, width, height): store a reference to the framebuffer and dimensions.
static mp_obj_t init(mp_obj_t framebuffer_obj, mp_obj_t width_obj, mp_obj_t height_obj) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(framebuffer_obj, &bufinfo, MP_BUFFER_WRITE);

    g_framebuffer = (uint16_t *)bufinfo.buf;
    g_framebuffer_len = bufinfo.len;
    g_framebuffer_width = (size_t)mp_obj_get_int(width_obj);
    g_framebuffer_height = (size_t)mp_obj_get_int(height_obj);

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(init_obj, init);

// render(): draw a moving black line on the RGB565 framebuffer as a deterministic test pattern.
static mp_obj_t render(void) {
    if (g_framebuffer == NULL || g_framebuffer_width == 0 || g_framebuffer_height == 0) {
        return mp_const_none;
    }

    uint16_t *pixels = g_framebuffer;
    const size_t len = g_framebuffer_len;
    const size_t width = g_framebuffer_width;
    const size_t height = g_framebuffer_height;
    const size_t max_pixels = len / sizeof(uint16_t);
    const size_t total_pixels = width * height;
    const size_t fill_pixels = (max_pixels < total_pixels) ? max_pixels : total_pixels;

    // Fill the framebuffer with white so the black line is visible.
    for (size_t i = 0; i < fill_pixels; i++) { pixels[i] = 0xFFFF; } // RGB565 white

    // Draw a horizontal black line across the current row.
    if (g_line_y < height) {
        const size_t base = g_line_y * width;
        for (size_t x = 0; x < width; x++) {
            const size_t idx = base + x;
            if (idx >= fill_pixels) {
                break;
            }
            pixels[idx] = 0x0000; // RGB565 black
        }
    }

    // Advance the line for the next call, wrapping at the bottom.
    g_line_y++;
    if (g_line_y >= height) {
        g_line_y = 0;
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(render_obj, render);

// move_paddle(delta): print delta for debugging.
static mp_obj_t move_paddle(mp_obj_t delta_obj) {
    int delta = mp_obj_get_int(delta_obj);
    mp_printf(&mp_plat_print, "delta: %d\n", delta);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(move_paddle_obj, move_paddle);

// This is the entry point and is called when the module is imported
mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args) {
    // This must be first, it sets up the globals dict and other things
    MP_DYNRUNTIME_INIT_ENTRY

    // Make the function available in the module's namespace
    mp_store_global(MP_QSTR_init, MP_OBJ_FROM_PTR(&init_obj));
    mp_store_global(MP_QSTR_render, MP_OBJ_FROM_PTR(&render_obj));
    mp_store_global(MP_QSTR_move_paddle, MP_OBJ_FROM_PTR(&move_paddle_obj));
    mp_store_global(MP_QSTR_readfile, MP_OBJ_FROM_PTR(&readfile_obj));

    // This must be last, it restores the globals dict
    MP_DYNRUNTIME_INIT_EXIT
}
