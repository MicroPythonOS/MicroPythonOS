// mp3dec - streaming MP3 (MPEG-1/2/2.5 Layer III) decoder for MicroPythonOS.
//
// Wraps the public-domain minimp3 decoder (c_mpos/minimp3). The Python side
// feeds compressed chunks and consumes 16-bit PCM through decode_into(), so
// the I2S buffer can be reused across frames without per-frame allocations.
//
// The decoder scratch area (about 16 KiB) is allocated on the heap by this
// module instead of minimp3's default stack frame: the audio thread only has a
// 16 KiB stack on ESP32.
//
// decode_into() buffers compressed input, so a caller must keep feeding (or
// draining with None/empty input) until it returns 0 before handing over more
// than the 16 KiB input buffer can hold at once: feed at most 14 KiB per call
// and drain between chunks.

#include "py/obj.h"
#include "py/runtime.h"
#include "py/mpthread.h"

#include <string.h>

#define MINIMP3_IMPLEMENTATION
#include "../minimp3/minimp3.h"

#define MP3DEC_INBUF_SIZE (16 * 1024)
#define MP3DEC_FRAME_BYTES (MINIMP3_MAX_SAMPLES_PER_FRAME * 2)
#define MP3DEC_MAX_FRAME 2048

typedef struct _mp3dec_obj_t {
    mp_obj_base_t base;
    mp3dec_t *dec;
    mp3dec_scratch_t *scratch;
    uint8_t *inbuf;
    int16_t *pcm;
    size_t in_len;
    size_t in_pos;
    size_t frame_len;
    mp3dec_frame_info_t info;
    uint32_t frames;
    uint32_t samples;
    uint32_t id3_bytes;
    uint8_t id3_state;
    uint32_t id3_skip;
    bool eof;
} mp3dec_obj_t;

static void mp3dec_release_buffers(mp3dec_obj_t *self) {
    if (self->dec) {
        m_free(self->dec);
        self->dec = NULL;
    }
    if (self->scratch) {
        m_free(self->scratch);
        self->scratch = NULL;
    }
    if (self->inbuf) {
        m_free(self->inbuf);
        self->inbuf = NULL;
    }
    if (self->pcm) {
        m_free(self->pcm);
        self->pcm = NULL;
    }
}

static mp_obj_t mp3dec_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    mp_arg_check_num(n_args, n_kw, 0, 0, false);
    mp3dec_obj_t *self = mp_obj_malloc_with_finaliser(mp3dec_obj_t, type);
    memset(&self->info, 0, sizeof(self->info));
    self->dec = NULL;
    self->scratch = NULL;
    self->inbuf = NULL;
    self->pcm = NULL;
    self->dec = m_malloc(sizeof(mp3dec_t));
    self->scratch = m_malloc(sizeof(mp3dec_scratch_t));
    self->inbuf = m_malloc(MP3DEC_INBUF_SIZE);
    self->pcm = m_malloc(MINIMP3_MAX_SAMPLES_PER_FRAME * sizeof(int16_t));
    mp3dec_init(self->dec);
    self->in_len = 0;
    self->in_pos = 0;
    self->frame_len = 0;
    self->frames = 0;
    self->samples = 0;
    self->id3_bytes = 0;
    self->id3_state = 0;
    self->id3_skip = 0;
    self->eof = false;
    return MP_OBJ_FROM_PTR(self);
}

static inline void mp3dec_compact(mp3dec_obj_t *self) {
    if (self->in_pos > 0) {
        size_t left = self->in_len - self->in_pos;
        if (left) {
            memmove(self->inbuf, self->inbuf + self->in_pos, left);
        }
        self->in_len = left;
        self->in_pos = 0;
    }
}

static void mp3dec_append(mp3dec_obj_t *self, const uint8_t *src, size_t len) {
    if (len == 0) {
        return;
    }
    mp3dec_compact(self);
    if (self->in_len + len > MP3DEC_INBUF_SIZE) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("mp3dec: input buffer overflow"));
    }
    memcpy(self->inbuf + self->in_len, src, len);
    self->in_len += len;
}

// Discard ID3v2 tags (including cover art) before the first audio frame.
static void mp3dec_skip_tags(mp3dec_obj_t *self) {
    for (;;) {
        size_t avail = self->in_len - self->in_pos;
        if (self->id3_state == 0) {
            if (avail < 10) {
                return;
            }
            uint8_t *p = self->inbuf + self->in_pos;
            if (p[0] == 'I' && p[1] == 'D' && p[2] == '3') {
                uint32_t size = ((uint32_t)(p[6] & 0x7f) << 21)
                    | ((uint32_t)(p[7] & 0x7f) << 14)
                    | ((uint32_t)(p[8] & 0x7f) << 7)
                    | (uint32_t)(p[9] & 0x7f);
                self->id3_skip = 10 + size + ((p[5] & 0x10) ? 10 : 0);
                self->id3_state = 1;
            } else {
                self->id3_state = 2;
                return;
            }
        }
        if (self->id3_state == 1) {
            if (self->id3_skip > avail) {
                self->id3_skip -= avail;
                self->id3_bytes += avail;
                self->in_pos = self->in_len;
                return;
            }
            self->in_pos += self->id3_skip;
            self->id3_bytes += self->id3_skip;
            self->id3_skip = 0;
            self->id3_state = 2;
        }
        return;
    }
}

static mp_obj_t mp3dec_decode_into(size_t n_args, const mp_obj_t *args) {
    mp3dec_obj_t *self = MP_OBJ_TO_PTR(args[0]);
    if (!self->dec) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("mp3dec: decoder is closed"));
    }

    if (args[1] != mp_const_none) {
        mp_buffer_info_t src;
        mp_get_buffer_raise(args[1], &src, MP_BUFFER_READ);
        mp3dec_append(self, src.buf, src.len);
    }

    mp_buffer_info_t dst;
    mp_get_buffer_raise(args[2], &dst, MP_BUFFER_WRITE);
    if (dst.len < MP3DEC_FRAME_BYTES) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("mp3dec: output buffer must be at least 4608 bytes"));
    }
    int shift = 0;
    if (n_args > 3) {
        shift = mp_obj_get_int(args[3]);
        if (shift < 0) {
            shift = 0;
        } else if (shift > 16) {
            shift = 16;
        }
    }

    uint8_t *out = dst.buf;
    size_t out_len = dst.len;
    size_t out_used = 0;
    bool out_full = false;
    uint32_t decoded_here = 0;

    for (;;) {
        mp3dec_skip_tags(self);
        size_t avail = self->in_len - self->in_pos;

        if (self->frame_len == 0) {
            if (avail < HDR_SIZE) {
                break;
            }
            const uint8_t *h = self->inbuf + self->in_pos;
            if (!hdr_valid(h) || HDR_GET_LAYER(h) != 1) {
                // Layer I/II shares the sync pattern but this module (and the
                // Python header parser) only handles Layer III.
                self->in_pos++;
                continue;
            }
            int flen = hdr_frame_bytes(h, 0) + hdr_padding(h);
            if (flen <= HDR_SIZE || flen > MP3DEC_MAX_FRAME) {
                self->in_pos++;
                continue;
            }
            self->frame_len = (size_t)flen;
        }

        avail = self->in_len - self->in_pos;
        if (avail < self->frame_len) {
            if (!self->eof) {
                break;
            }
            // Truncated tail: skip a byte and look for the next header.
            self->in_pos++;
            self->frame_len = 0;
            continue;
        }
        if (out_len - out_used < MP3DEC_FRAME_BYTES) {
            out_full = true;
            break;
        }

        mp3dec_frame_info_t info;
        memset(&info, 0, sizeof(info));
        int samples;
        MP_THREAD_GIL_EXIT();
        samples = mp3dec_decode_frame(self->dec, self->scratch, self->inbuf + self->in_pos,
                                      (int)self->frame_len, self->pcm, &info);
        MP_THREAD_GIL_ENTER();

        if (samples > 0) {
            self->in_pos += self->frame_len;
        } else {
            // Not a real frame (a false sync inside payload data, or a frame
            // that could not be decoded): move on one byte and resync.
            self->in_pos++;
        }
        self->frame_len = 0;

        if (samples > 0) {
            size_t count = (size_t)samples * info.channels;
            uint8_t *d = out + out_used;
            const int16_t *s = self->pcm;
            if (shift == 0) {
                memcpy(d, s, count * sizeof(int16_t));
            } else if (shift >= 16) {
                memset(d, 0, count * sizeof(int16_t));
            } else {
                for (size_t i = 0; i < count; i++) {
                    int16_t value = (int16_t)(s[i] >> shift);
                    d[i * 2] = (uint8_t)value;
                    d[i * 2 + 1] = (uint8_t)((uint16_t)value >> 8);
                }
            }
            out_used += count * sizeof(int16_t);
            self->frames++;
            self->samples += (uint32_t)samples;
            self->info = info;
            decoded_here++;
        }
    }

    mp3dec_compact(self);
    if (self->eof && !out_full && decoded_here == 0) {
        self->in_len = 0;
        self->in_pos = 0;
    }
    return mp_obj_new_int_from_uint(out_used);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp3dec_decode_into_obj, 3, 4, mp3dec_decode_into);

static mp_obj_t mp3dec_finish(mp_obj_t self_in) {
    mp3dec_obj_t *self = MP_OBJ_TO_PTR(self_in);
    self->eof = true;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp3dec_finish_obj, mp3dec_finish);

static mp_obj_t mp3dec_reset(mp_obj_t self_in) {
    mp3dec_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (!self->dec) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("mp3dec: decoder is closed"));
    }
    mp3dec_init(self->dec);
    self->in_len = 0;
    self->in_pos = 0;
    self->frame_len = 0;
    self->frames = 0;
    self->samples = 0;
    self->id3_bytes = 0;
    self->id3_state = 0;
    self->id3_skip = 0;
    self->eof = false;
    memset(&self->info, 0, sizeof(self->info));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp3dec_reset_obj, mp3dec_reset);

// (sample_rate, channels, bitrate_kbps, layer, frame_bytes, frames, samples, id3_bytes)
static mp_obj_t mp3dec_info(mp_obj_t self_in) {
    mp3dec_obj_t *self = MP_OBJ_TO_PTR(self_in);
    mp_obj_t items[] = {
        mp_obj_new_int(self->info.hz),
        mp_obj_new_int(self->info.channels),
        mp_obj_new_int(self->info.bitrate_kbps),
        mp_obj_new_int(self->info.layer),
        mp_obj_new_int(self->info.frame_bytes),
        mp_obj_new_int_from_uint(self->frames),
        mp_obj_new_int_from_uint(self->samples),
        mp_obj_new_int_from_uint(self->id3_bytes),
    };
    return mp_obj_new_tuple(MP_ARRAY_SIZE(items), items);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp3dec_info_obj, mp3dec_info);

static mp_obj_t mp3dec_close(mp_obj_t self_in) {
    mp3dec_obj_t *self = MP_OBJ_TO_PTR(self_in);
    mp3dec_release_buffers(self);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp3dec_close_obj, mp3dec_close);

static mp_obj_t mp3dec_del(mp_obj_t self_in) {
    mp3dec_release_buffers(MP_OBJ_TO_PTR(self_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp3dec_del_obj, mp3dec_del);

static const mp_rom_map_elem_t mp3dec_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_decode_into), MP_ROM_PTR(&mp3dec_decode_into_obj) },
    { MP_ROM_QSTR(MP_QSTR_finish), MP_ROM_PTR(&mp3dec_finish_obj) },
    { MP_ROM_QSTR(MP_QSTR_reset), MP_ROM_PTR(&mp3dec_reset_obj) },
    { MP_ROM_QSTR(MP_QSTR_info), MP_ROM_PTR(&mp3dec_info_obj) },
    { MP_ROM_QSTR(MP_QSTR_close), MP_ROM_PTR(&mp3dec_close_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&mp3dec_del_obj) },
};
static MP_DEFINE_CONST_DICT(mp3dec_locals_dict, mp3dec_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    mp3dec_type,
    MP_QSTR_Decoder,
    MP_TYPE_FLAG_NONE,
    make_new, mp3dec_make_new,
    locals_dict, &mp3dec_locals_dict
);

static const mp_rom_map_elem_t mp3dec_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_mp3dec) },
    { MP_ROM_QSTR(MP_QSTR_Decoder), MP_ROM_PTR(&mp3dec_type) },
    { MP_ROM_QSTR(MP_QSTR_FRAME_BYTES), MP_ROM_INT(MP3DEC_FRAME_BYTES) },
};
static MP_DEFINE_CONST_DICT(mp3dec_module_globals, mp3dec_module_globals_table);

const mp_obj_module_t mp3dec_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mp3dec_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_mp3dec, mp3dec_user_cmodule);
