#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "py/obj.h"
#include "py/runtime.h"
#include "py/mperrno.h"

// On the ESP32 port py/runtime.h already pulls in FreeRTOS (via
// mpthreadport.h), which defines INC_FREERTOS_H and declares the real
// uxTaskGetStackHighWaterMark; only desktop/web builds need the stub.
// Keying on __xtensa__ (as before) broke the RISC-V ESP32-P4 build with a
// conflicting prototype, and ESP_PLATFORM is not set for this compile unit.
#if defined(INC_FREERTOS_H) || defined(ESP_PLATFORM) || defined(__xtensa__)
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#else
size_t uxTaskGetStackHighWaterMark(void * unused) {
    return 99999999;
}
#endif

#include "../quirc/lib/quirc.h"
#include "../quirc/lib/quirc_internal.h"  // Exposes full struct quirc

#define QRDECODE_DEBUG_PRINT(...) mp_printf(&mp_plat_print, __VA_ARGS__)

// One decoder is kept between calls, so live scanning doesn't allocate and free
// quirc's frame-sized buffers for every frame. It is reallocated when the frame
// size changes and freed by qrdecode.release(). It is module state without a lock:
// qrdecode must be called from one thread only.
struct qrdecode_state {
    struct quirc *qr;
    struct quirc_code code;
    struct quirc_data data;
};

static struct qrdecode_state *qrdecode_state;

// Where the decoder is allocated, in one place. It is kept for as long as QR
// scanning is on, so all of it comes from ps_malloc() (quirc_internal.h), which
// prefers PSRAM and leaves the scarce internal RAM to the display and camera DMA
// buffers: struct quirc, its frame-sized buffer and its flood-fill stack from
// quirc_new() and quirc_resize(), and the code and data structs from here. All of
// it is freed with free(), here or in quirc_destroy(); on ESP-IDF, free() also
// releases memory from heap_caps_malloc().
static struct quirc *qrdecode_new_quirc(void) {
    return quirc_new();
}

static struct qrdecode_state *qrdecode_new_state(void) {
    return ps_malloc(sizeof(struct qrdecode_state));
}

// Returns the decoder, sized for width x height. Raises OSError(ENOMEM) when it
// can't be allocated, leaving qrdecode_state consistent for the next call.
static struct qrdecode_state *qrdecode_get_state(int width, int height) {
    struct qrdecode_state *state = qrdecode_state;
    if (!state) {
        state = qrdecode_new_state();
        if (!state) {
            mp_raise_OSError(MP_ENOMEM);
        }
        state->qr = NULL;
        qrdecode_state = state;
    }
    if (state->qr) {
        int w, h;
        quirc_begin(state->qr, &w, &h);
        if (w == width && h == height) {
            return state;
        }
        // Free the old buffers before allocating new ones, so both are never held at once.
        // The pointer is cleared first, so an exception (Ctrl-C) can't leave it dangling.
        struct quirc *old = state->qr;
        state->qr = NULL;
        quirc_destroy(old);
    }
    struct quirc *qr = qrdecode_new_quirc();
    if (!qr) {
        mp_raise_OSError(MP_ENOMEM);
    }
    if (quirc_resize(qr, width, height) < 0) {
        quirc_destroy(qr);
        mp_raise_OSError(MP_ENOMEM);
    }
    state->qr = qr;
    return state;
}

// Decodes the first code found by the last quirc_end() or quirc_end_from().
static mp_obj_t qrdecode_result(struct qrdecode_state *state) {
    int count = quirc_count(state->qr);
    if (count == 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("no QR code found"));
    }

    quirc_extract(state->qr, 0, &state->code);
    // the code struct now contains the corners of the QR code, as well as the bitmap of the values
    // this could be used to display debug info to the user - they might even be able to see which modules are being misidentified!

    int err = quirc_decode(&state->code, &state->data);
    if (err != QUIRC_SUCCESS) {
        mp_raise_TypeError(MP_ERROR_TEXT("failed to decode QR code"));
    }

    return mp_obj_new_bytes((const uint8_t *)state->data.payload, state->data.payload_len);
}

// Raises ValueError unless quirc can take a width x height frame: quirc counts
// pixels in an int, and an RGB565 frame is twice that many bytes. A product that
// wrapped around would pass the buffer size check and size quirc's buffers too
// small for the rows it then scans.
static void qrdecode_check_size(mp_int_t width, mp_int_t height) {
    if (width <= 0 || height <= 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("width and height must be positive"));
    }
    if (width > INT_MAX / 2 / height) {
        mp_raise_ValueError(MP_ERROR_TEXT("frame too large"));
    }
}

static mp_obj_t qrdecode(mp_uint_t n_args, const mp_obj_t *args) {
    //QRDECODE_DEBUG_PRINT("qrdecode: Starting\n");
    //QRDECODE_DEBUG_PRINT("qrdecode: Stack high-water mark: %u bytes\n", uxTaskGetStackHighWaterMark(NULL));

    if (n_args != 3) {
        mp_raise_ValueError(MP_ERROR_TEXT("quirc_decode expects 3 arguments: buffer, width, height"));
    }

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_READ);

    mp_int_t width = mp_obj_get_int(args[1]);
    mp_int_t height = mp_obj_get_int(args[2]);
    //QRDECODE_DEBUG_PRINT("qrdecode: Width=%u, Height=%u\n", width, height);

    qrdecode_check_size(width, height);
    if (bufinfo.len != (size_t)(width * height)) {
        QRDECODE_DEBUG_PRINT("qrdecode wrong bufsize: %u bytes\n", bufinfo.len);
        mp_raise_ValueError(MP_ERROR_TEXT("buffer size must match width * height"));
    }
    struct qrdecode_state *state = qrdecode_get_state(width, height);

    // quirc_end_from() only reads the caller's buffer, which may be a camera frame
    // that is also being displayed by lvgl, and thresholds it into quirc's own buffer.
    quirc_end_from(state->qr, bufinfo.buf);

    // now num_grids is set, as well as others, probably

    return qrdecode_result(state);
}

static mp_obj_t qrdecode_rgb565(mp_uint_t n_args, const mp_obj_t *args) {
    //QRDECODE_DEBUG_PRINT("qrdecode_rgb565: Starting\n");

    if (n_args != 3) {
        mp_raise_ValueError(MP_ERROR_TEXT("qrdecode_rgb565 expects 3 arguments: buffer, width, height"));
    }

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_READ);

    mp_int_t width = mp_obj_get_int(args[1]);
    mp_int_t height = mp_obj_get_int(args[2]);
    //QRDECODE_DEBUG_PRINT("qrdecode_rgb565: Width=%u, Height=%u\n", width, height);

    qrdecode_check_size(width, height);
    if (bufinfo.len != (size_t)(width * height * 2)) {
        QRDECODE_DEBUG_PRINT("qrdecode_rgb565 wrong bufsize: %u bytes\n", bufinfo.len);
        mp_raise_ValueError(MP_ERROR_TEXT("buffer size must match width * height * 2 for RGB565"));
    }

    struct qrdecode_state *state = qrdecode_get_state(width, height);
    uint8_t *gray_buffer = quirc_begin(state->qr, NULL, NULL);

    uint16_t *rgb565 = (uint16_t *)bufinfo.buf;
    for (size_t i = 0; i < (size_t)(width * height); i++) {
        uint16_t pixel = rgb565[i];
        uint8_t r = ((pixel >> 11) & 0x1F) << 3;
        uint8_t g = ((pixel >> 5) & 0x3F) << 2;
        uint8_t b = (pixel & 0x1F) << 3;
        gray_buffer[i] = (uint8_t)((0.299 * r + 0.587 * g + 0.114 * b) + 0.5);
    }
    quirc_end(state->qr);

    return qrdecode_result(state);
}

static mp_obj_t qrdecode_release(void) {
    struct qrdecode_state *state = qrdecode_state;
    if (state) {
        // Cleared before anything is freed, so an exception (Ctrl-C) can't leave it dangling
        qrdecode_state = NULL;
        if (state->qr) {
            quirc_destroy(state->qr);
        }
        free(state);
    }
    return mp_const_none;
}

static mp_obj_t qrdecode_wrapper(size_t n_args, const mp_obj_t *args) {
    return qrdecode(n_args, args);
}

static mp_obj_t qrdecode_rgb565_wrapper(size_t n_args, const mp_obj_t *args) {
    return qrdecode_rgb565(n_args, args);
}

static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(qrdecode_obj, 3, 3, qrdecode_wrapper);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(qrdecode_rgb565_obj, 3, 3, qrdecode_rgb565_wrapper);
static MP_DEFINE_CONST_FUN_OBJ_0(qrdecode_release_obj, qrdecode_release);

static const mp_rom_map_elem_t qrdecode_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_qrdecode) },
    { MP_ROM_QSTR(MP_QSTR_qrdecode), MP_ROM_PTR(&qrdecode_obj) },
    { MP_ROM_QSTR(MP_QSTR_qrdecode_rgb565), MP_ROM_PTR(&qrdecode_rgb565_obj) },
    { MP_ROM_QSTR(MP_QSTR_release), MP_ROM_PTR(&qrdecode_release_obj) },
};

static MP_DEFINE_CONST_DICT(qrdecode_module_globals, qrdecode_module_globals_table);

const mp_obj_module_t qrdecode_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&qrdecode_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_qrdecode, qrdecode_module);
