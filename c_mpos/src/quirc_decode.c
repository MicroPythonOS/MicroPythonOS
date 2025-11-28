#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "py/obj.h"
#include "py/runtime.h"
#include "py/mperrno.h"
#include "py/nlr.h" // Include for nlr_buf_t

#ifdef __xtensa__
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

static mp_obj_t qrdecode(mp_uint_t n_args, const mp_obj_t *args) {
    QRDECODE_DEBUG_PRINT("qrdecode: Starting\n");
    QRDECODE_DEBUG_PRINT("qrdecode: Stack high-water mark: %u bytes\n", uxTaskGetStackHighWaterMark(NULL));

    if (n_args != 3) {
        mp_raise_ValueError(MP_ERROR_TEXT("quirc_decode expects 3 arguments: buffer, width, height"));
    }

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_READ);

    mp_int_t width = mp_obj_get_int(args[1]);
    mp_int_t height = mp_obj_get_int(args[2]);
    QRDECODE_DEBUG_PRINT("qrdecode: Width=%u, Height=%u\n", width, height);

    if (width <= 0 || height <= 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("width and height must be positive"));
    }
    if (bufinfo.len != (size_t)(width * height)) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer size must match width * height"));
    }

    struct quirc *qr = quirc_new();
    if (!qr) {
        mp_raise_OSError(MP_ENOMEM);
    }
    //QRDECODE_DEBUG_PRINT("qrdecode: Allocated quirc object\n");

    if (quirc_resize(qr, width, height) < 0) {
        quirc_destroy(qr);
        mp_raise_OSError(MP_ENOMEM);
    }
    //QRDECODE_DEBUG_PRINT("qrdecode: Resized quirc object\n");

    uint8_t *image = quirc_begin(qr, NULL, NULL);
    memcpy(image, bufinfo.buf, width * height);
    // would be nice to be able to use the existing buffer (bufinfo.buf) here, avoiding memcpy,
    // but that buffer is also being filled by image capture and displayed by lvgl
    // and that becomes unstable... it shows black artifacts and crashes sometimes...
    //uint8_t *temp_image = image;
    //image = bufinfo.buf;
    //qr->image = bufinfo.buf; // if this works then we can also eliminate quirc's ps_alloc()
    quirc_end(qr);
    //qr->image = temp_image; // restore, because quirc will try to free it

    /*
    // Pointer swap - NO memcpy, NO internal.h needed
    uint8_t *quirc_buffer = quirc_begin(qr, NULL, NULL);
    uint8_t *saved_bufinfo = bufinfo.buf;
    bufinfo.buf = quirc_buffer;  // quirc now uses your buffer
    quirc_end(qr);               // QR detection works!
    // Restore your buffer pointer
    //bufinfo.buf = saved_bufinfo;
    */

    // now num_grids is set, as well as others, probably

    int count = quirc_count(qr);
    if (count == 0) {
        // Restore your buffer pointer
        quirc_destroy(qr);
        //QRDECODE_DEBUG_PRINT("qrdecode: No QR code found, freed quirc object\n");
        mp_raise_ValueError(MP_ERROR_TEXT("no QR code found"));
    }

    struct quirc_code *code = (struct quirc_code *)malloc(sizeof(struct quirc_code));
    if (!code) {
        quirc_destroy(qr);
        mp_raise_OSError(MP_ENOMEM);
    }
    //QRDECODE_DEBUG_PRINT("qrdecode: Allocated quirc_code\n");
    quirc_extract(qr, 0, code);
    // the code struct now contains the corners of the QR code, as well as the bitmap of the values
    // this could be used to display debug info to the user - they might even be able to see which modules are being misidentified!

    struct quirc_data *data = (struct quirc_data *)malloc(sizeof(struct quirc_data));
    if (!data) {
        free(code);
        quirc_destroy(qr);
        mp_raise_OSError(MP_ENOMEM);
    }
    //QRDECODE_DEBUG_PRINT("qrdecode: Allocated quirc_data\n");

    int err = quirc_decode(code, data);
    if (err != QUIRC_SUCCESS) {
        free(data);
        free(code);
        quirc_destroy(qr);
        QRDECODE_DEBUG_PRINT("qrdecode: Decode failed, freed data, code, and quirc object\n");
        mp_raise_TypeError(MP_ERROR_TEXT("failed to decode QR code"));
    }

    mp_obj_t result = mp_obj_new_bytes((const uint8_t *)data->payload, data->payload_len);

    free(data);
    free(code);
    quirc_destroy(qr);
    //QRDECODE_DEBUG_PRINT("qrdecode: Freed data, code, and quirc object, returning result\n");
    return result;
}

static mp_obj_t qrdecode_rgb565(mp_uint_t n_args, const mp_obj_t *args) {
    QRDECODE_DEBUG_PRINT("qrdecode_rgb565: Starting\n");

    if (n_args != 3) {
        mp_raise_ValueError(MP_ERROR_TEXT("qrdecode_rgb565 expects 3 arguments: buffer, width, height"));
    }

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_READ);

    mp_int_t width = mp_obj_get_int(args[1]);
    mp_int_t height = mp_obj_get_int(args[2]);
    QRDECODE_DEBUG_PRINT("qrdecode_rgb565: Width=%u, Height=%u\n", width, height);

    if (width <= 0 || height <= 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("width and height must be positive"));
    }
    if (bufinfo.len != (size_t)(width * height * 2)) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer size must match width * height * 2 for RGB565"));
    }

    uint8_t *gray_buffer = (uint8_t *)malloc(width * height * sizeof(uint8_t));
    if (!gray_buffer) {
        mp_raise_OSError(MP_ENOMEM);
    }
    QRDECODE_DEBUG_PRINT("qrdecode_rgb565: Allocated gray_buffer (%u bytes)\n", width * height * sizeof(uint8_t));

    uint16_t *rgb565 = (uint16_t *)bufinfo.buf;
    for (size_t i = 0; i < (size_t)(width * height); i++) {
        uint16_t pixel = rgb565[i];
        uint8_t r = ((pixel >> 11) & 0x1F) << 3;
        uint8_t g = ((pixel >> 5) & 0x3F) << 2;
        uint8_t b = (pixel & 0x1F) << 3;
        gray_buffer[i] = (uint8_t)((0.299 * r + 0.587 * g + 0.114 * b) + 0.5);
    }

    mp_obj_t gray_args[3] = {
        mp_obj_new_bytes(gray_buffer, width * height),
        mp_obj_new_int(width),
        mp_obj_new_int(height)
    };

    mp_obj_t result = mp_const_none;
    nlr_buf_t exception_handler;
    if (nlr_push(&exception_handler) == 0) {
        result = qrdecode(3, gray_args);
        nlr_pop();
        QRDECODE_DEBUG_PRINT("qrdecode_rgb565: qrdecode succeeded, freeing gray_buffer\n");
        free(gray_buffer);
    } else {
        QRDECODE_DEBUG_PRINT("qrdecode_rgb565: Exception caught, freeing gray_buffer\n");
        // Cleanup
        if (gray_buffer) {
            free(gray_buffer);
            gray_buffer = NULL;
        }
        //mp_raise_TypeError(MP_ERROR_TEXT("qrdecode_rgb565: failed to decode QR code"));
        // Re-raising the exception results in an Unhandled exception in thread started by <function qrdecode_live at 0x7f6f55af0680>
        // which isn't caught, even when catching Exception, so this looks like a bug in MicroPython...
        nlr_pop();
        nlr_raise(exception_handler.ret_val);
        // Re-raise the original exception with optional additional message
        /*
        mp_raise_msg_and_obj(
            mp_obj_exception_get_type(exception_handler.ret_val),
            MP_OBJ_NEW_QSTR(qstr_from_str("qrdecode_rgb565: failed during processing")),
            exception_handler.ret_val
        );
        */
        // Re-raise as new exception of same type, with message + original as arg
        // (embeds original for traceback chaining)
        // crashes:
        //const mp_obj_type_t *exc_type = mp_obj_get_type(exception_handler.ret_val);
        //mp_raise_msg_varg(exc_type, MP_ERROR_TEXT("qrdecode_rgb565: failed during processing: %q"), exception_handler.ret_val);
    }

        //nlr_pop(); maybe it needs to be done after instead of before the re-raise?

    return result;
}

static mp_obj_t qrdecode_wrapper(size_t n_args, const mp_obj_t *args) {
    return qrdecode(n_args, args);
}

static mp_obj_t qrdecode_rgb565_wrapper(size_t n_args, const mp_obj_t *args) {
    return qrdecode_rgb565(n_args, args);
}

static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(qrdecode_obj, 3, 3, qrdecode_wrapper);
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(qrdecode_rgb565_obj, 3, 3, qrdecode_rgb565_wrapper);

static const mp_rom_map_elem_t qrdecode_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_qrdecode) },
    { MP_ROM_QSTR(MP_QSTR_qrdecode), MP_ROM_PTR(&qrdecode_obj) },
    { MP_ROM_QSTR(MP_QSTR_qrdecode_rgb565), MP_ROM_PTR(&qrdecode_rgb565_obj) },
};

static MP_DEFINE_CONST_DICT(qrdecode_module_globals, qrdecode_module_globals_table);

const mp_obj_module_t qrdecode_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&qrdecode_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_qrdecode, qrdecode_module);
