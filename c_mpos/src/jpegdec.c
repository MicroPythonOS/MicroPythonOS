/*
 * jpegdec: MicroPython binding for Espressif's esp_new_jpeg decoder.
 *
 * Decodes a baseline/progressive JPEG held in a Python buffer straight into a
 * caller-supplied RGB565 (little-endian) buffer, which can then be shown
 * through an lv.image_dsc_t of cf=RGB565 with no further decoding by LVGL.
 * Written for MJPEG video playback (ClipTV), where LVGL's own TJpgDec path
 * was 100 ms per 160x120 frame and kept every decoded frame in a
 * pointer-keyed cache.
 *
 *   jpegdec.info(jpeg) -> (width, height)
 *   jpegdec.decode(jpeg, out, scale_w=0, scale_h=0) -> (width, height)
 *       out: writable buffer of at least width*height*2 bytes, 16-byte aligned
 *            (a bytearray from the MicroPython heap is).
 *       scale_w/scale_h: optional downscale target (multiples of 8, at most 1/8).
 *
 * ESP32 only (the decoder library ships as a prebuilt for esp32/s2/s3/p4).
 */
#include <stdint.h>
#include <string.h>

#include "py/runtime.h"
#include "py/obj.h"

#include "esp_jpeg_common.h"
#include "esp_jpeg_dec.h"

static jpeg_dec_handle_t dec_handle = NULL;
static int dec_scale_w = 0;
static int dec_scale_h = 0;

static jpeg_dec_handle_t jpegdec_get_handle(int scale_w, int scale_h) {
    if (dec_handle != NULL && scale_w == dec_scale_w && scale_h == dec_scale_h) {
        return dec_handle;
    }
    if (dec_handle != NULL) {
        jpeg_dec_close(dec_handle);
        dec_handle = NULL;
    }
    jpeg_dec_config_t cfg = DEFAULT_JPEG_DEC_CONFIG();
    cfg.output_type = JPEG_PIXEL_FORMAT_RGB565_LE;
    cfg.scale.width = scale_w;
    cfg.scale.height = scale_h;
    if (jpeg_dec_open(&cfg, &dec_handle) != JPEG_ERR_OK || dec_handle == NULL) {
        dec_handle = NULL;
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("jpeg_dec_open failed"));
    }
    dec_scale_w = scale_w;
    dec_scale_h = scale_h;
    return dec_handle;
}

static void jpegdec_raise(jpeg_error_t err) {
    switch (err) {
        case JPEG_ERR_NO_MEM:
            mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("jpeg decoder out of memory"));
        case JPEG_ERR_NO_MORE_DATA:
            mp_raise_ValueError(MP_ERROR_TEXT("truncated JPEG"));
        case JPEG_ERR_UNSUPPORT_FMT:
        case JPEG_ERR_UNSUPPORT_STD:
            mp_raise_ValueError(MP_ERROR_TEXT("unsupported JPEG variant"));
        default:
            mp_raise_ValueError(MP_ERROR_TEXT("bad JPEG data"));
    }
}

static mp_obj_t jpegdec_info(mp_obj_t jpeg_in) {
    mp_buffer_info_t jpeg;
    mp_get_buffer_raise(jpeg_in, &jpeg, MP_BUFFER_READ);
    jpeg_dec_handle_t handle = jpegdec_get_handle(0, 0);
    jpeg_dec_io_t io = {0};
    io.inbuf = (uint8_t *)jpeg.buf;
    io.inbuf_len = (int)jpeg.len;
    jpeg_dec_header_info_t hdr = {0};
    jpeg_error_t err = jpeg_dec_parse_header(handle, &io, &hdr);
    if (err != JPEG_ERR_OK) {
        jpegdec_raise(err);
    }
    mp_obj_t items[2] = { MP_OBJ_NEW_SMALL_INT(hdr.width), MP_OBJ_NEW_SMALL_INT(hdr.height) };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_1(jpegdec_info_obj, jpegdec_info);

static mp_obj_t jpegdec_decode(size_t n_args, const mp_obj_t *args) {
    mp_buffer_info_t jpeg;
    mp_get_buffer_raise(args[0], &jpeg, MP_BUFFER_READ);
    mp_buffer_info_t out;
    mp_get_buffer_raise(args[1], &out, MP_BUFFER_WRITE);
    int scale_w = n_args > 2 ? mp_obj_get_int(args[2]) : 0;
    int scale_h = n_args > 3 ? mp_obj_get_int(args[3]) : 0;
    if (scale_w < 0 || scale_h < 0 || (scale_w % 8) != 0 || (scale_h % 8) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("scale must be multiples of 8"));
    }
    if (((uintptr_t)out.buf & 15) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("out buffer must be 16-byte aligned"));
    }

    jpeg_dec_handle_t handle = jpegdec_get_handle(scale_w, scale_h);
    jpeg_dec_io_t io = {0};
    io.inbuf = (uint8_t *)jpeg.buf;
    io.inbuf_len = (int)jpeg.len;
    jpeg_dec_header_info_t hdr = {0};
    jpeg_error_t err = jpeg_dec_parse_header(handle, &io, &hdr);
    if (err != JPEG_ERR_OK) {
        jpegdec_raise(err);
    }
    int out_w = scale_w ? scale_w : hdr.width;
    int out_h = scale_h ? scale_h : hdr.height;
    int needed = 0;
    if (jpeg_dec_get_outbuf_len(handle, &needed) != JPEG_ERR_OK || needed <= 0) {
        needed = out_w * out_h * 2;
    }
    if ((int)out.len < needed) {
        mp_raise_ValueError(MP_ERROR_TEXT("out buffer too small"));
    }
    io.outbuf = (uint8_t *)out.buf;
    err = jpeg_dec_process(handle, &io);
    if (err != JPEG_ERR_OK) {
        jpegdec_raise(err);
    }
    mp_obj_t items[2] = { MP_OBJ_NEW_SMALL_INT(out_w), MP_OBJ_NEW_SMALL_INT(out_h) };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(jpegdec_decode_obj, 2, 4, jpegdec_decode);

static const mp_rom_map_elem_t jpegdec_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_jpegdec) },
    { MP_ROM_QSTR(MP_QSTR_info), MP_ROM_PTR(&jpegdec_info_obj) },
    { MP_ROM_QSTR(MP_QSTR_decode), MP_ROM_PTR(&jpegdec_decode_obj) },
};
static MP_DEFINE_CONST_DICT(jpegdec_module_globals, jpegdec_module_globals_table);

const mp_obj_module_t jpegdec_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&jpegdec_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_jpegdec, jpegdec_module);
