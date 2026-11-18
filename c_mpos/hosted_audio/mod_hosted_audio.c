// SPDX-License-Identifier: MIT
//
// hosted_audio - PCM playback for the hosts that have no machine.I2S.
//
// A badge has an i2s DAC and a piezo driver; a desktop and a browser have
// neither, which left every app that synthesises its own samples (a game
// engine's mixer, a soft synth) silent there. This module is the missing sink:
// int16 frames straight to the host's default audio device.
//
// The API is the shape `mpos.audio.pcm_stream.PcmSink` already uses - open,
// write, close - so it is a backend, not a second abstraction:
//
//   hosted_audio.open(rate=11025, channels=1)
//   hosted_audio.write(buffer)   # int16 frames, blocks only when the buffer is full
//   hosted_audio.close()
//   hosted_audio.active()
//
// The backend is SDL's audio (see micropython.mk): Emscripten implements it over
// WebAudio, and a desktop SDL build uses ALSA/CoreAudio/Pulse behind the same
// API. That is deliberate - it is the one audio stack already in every build,
// so this module needs no new dependency, and it keeps the plugin/mixing layer
// (PulseAudio, PipeWire, dmix) working, which talking to /dev/snd directly
// would not.
//
// The browser needs a user gesture before it will start an AudioContext; SDL
// resumes it on the first interaction with the page, which the OS gets as soon
// as anybody touches the UI.

#include <string.h>

#include "py/runtime.h"
#include "py/obj.h"

#if MICROPY_PY_HOSTED_AUDIO

#if MICROPY_PY_HOSTED_AUDIO_SDL

// -- SDL audio (web: WebAudio through Emscripten's SDL2 port) ----------------

#include "SDL2/SDL.h"

static SDL_AudioDeviceID s_device;
static unsigned int s_rate;
static int s_channels;

static void close_device(void) {
    if (s_device != 0) {
        SDL_CloseAudioDevice(s_device);
        s_device = 0;
    }
}

static mp_obj_t hosted_audio_open(size_t n_args, const mp_obj_t *pos_args,
                                 mp_map_t *kw_args) {
    enum { ARG_rate, ARG_channels };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_rate, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = 11025 } },
        { MP_QSTR_channels, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = 1 } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, args);

    close_device();
    s_rate = (unsigned int)args[ARG_rate].u_int;
    s_channels = args[ARG_channels].u_int;
    if (s_channels < 1) {
        s_channels = 1;
    }
    if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("sdl audio: %s"),
                          SDL_GetError());
    }
    SDL_AudioSpec want;
    memset(&want, 0, sizeof(want));
    want.freq = (int)s_rate;
    want.format = AUDIO_S16LSB;
    want.channels = (Uint8)s_channels;
    // ~40 ms at 11 kHz: comfortable for effects, and one buffer of slack for
    // a frame that arrives late.
    want.samples = 512;
    s_device = SDL_OpenAudioDevice(NULL, 0, &want, NULL, 0);
    if (s_device == 0) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("sdl audio open: %s"),
                          SDL_GetError());
    }
    SDL_PauseAudioDevice(s_device, 0);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(hosted_audio_open_obj, 0, hosted_audio_open);

static mp_obj_t hosted_audio_write(mp_obj_t buffer) {
    if (s_device == 0) {
        return mp_obj_new_int(0);
    }
    mp_buffer_info_t info;
    mp_get_buffer_raise(buffer, &info, MP_BUFFER_READ);
    if (info.len == 0) {
        return mp_obj_new_int(0);
    }
    // Queue rather than push: the audio thread drains it at its own rate, so a
    // frame that runs late does not have to wait for the device.
    if (SDL_QueueAudio(s_device, info.buf, (Uint32)info.len) != 0) {
        return mp_obj_new_int(0);
    }
    return mp_obj_new_int((int)info.len);
}
static MP_DEFINE_CONST_FUN_OBJ_1(hosted_audio_write_obj, hosted_audio_write);

static mp_obj_t hosted_audio_close(void) {
    close_device();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(hosted_audio_close_obj, hosted_audio_close);

static mp_obj_t hosted_audio_active(void) {
    return mp_obj_new_bool(s_device != 0);
}
static MP_DEFINE_CONST_FUN_OBJ_0(hosted_audio_active_obj, hosted_audio_active);

static mp_obj_t hosted_audio_rate(void) {
    return mp_obj_new_int((mp_int_t)s_rate);
}
static MP_DEFINE_CONST_FUN_OBJ_0(hosted_audio_rate_obj, hosted_audio_rate);

#endif  // backend

static const mp_rom_map_elem_t hosted_audio_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_hosted_audio) },
    { MP_ROM_QSTR(MP_QSTR_open), MP_ROM_PTR(&hosted_audio_open_obj) },
    { MP_ROM_QSTR(MP_QSTR_write), MP_ROM_PTR(&hosted_audio_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_close), MP_ROM_PTR(&hosted_audio_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_active), MP_ROM_PTR(&hosted_audio_active_obj) },
    { MP_ROM_QSTR(MP_QSTR_rate), MP_ROM_PTR(&hosted_audio_rate_obj) },
};
static MP_DEFINE_CONST_DICT(hosted_audio_globals, hosted_audio_globals_table);

const mp_obj_module_t hosted_audio_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&hosted_audio_globals,
};

MP_REGISTER_MODULE(MP_QSTR_hosted_audio, hosted_audio_module);

#endif  // MICROPY_PY_HOSTED_AUDIO
