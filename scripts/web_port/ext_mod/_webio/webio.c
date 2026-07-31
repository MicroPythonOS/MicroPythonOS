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

EM_JS(void, webio_js_audio_init, (void), {
    var H = Module.__webio || (Module.__webio = {});
    if (H.audio) return;
    var AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    var A = H.audio = {
        context: new AudioContext(),
        oscillator: null,
        toneGain: null,
        source: null,
        sourceGain: null,
        generation: 0
    };
    var unlock = function() {
        if (A.context.state === "suspended") {
            A.context.resume().catch(function() {});
        }
    };
    document.addEventListener("pointerdown", unlock, true);
    document.addEventListener("keydown", unlock, true);
    document.addEventListener("touchstart", unlock, true);
});

EM_JS(void, webio_js_tone, (int frequency, int duty), {
    var H = Module.__webio;
    if (!H || !H.audio) return;
    var A = H.audio;
    if (!A.oscillator) {
        A.oscillator = A.context.createOscillator();
        A.oscillator.type = "square";
        A.toneGain = A.context.createGain();
        A.toneGain.gain.value = 0;
        A.oscillator.connect(A.toneGain);
        A.toneGain.connect(A.context.destination);
        A.oscillator.start();
    }
    var now = A.context.currentTime;
    A.oscillator.frequency.setValueAtTime(Math.max(1, frequency), now);
    A.toneGain.gain.setValueAtTime(frequency > 0 ? Math.min(0.2, duty / 163840.0) : 0, now);
});

EM_JS(void, webio_js_tone_stop, (void), {
    var H = Module.__webio;
    if (!H || !H.audio || !H.audio.oscillator) return;
    var A = H.audio;
    try { A.oscillator.stop(); } catch (e) {}
    A.oscillator.disconnect();
    A.toneGain.disconnect();
    A.oscillator = null;
    A.toneGain = null;
});

EM_JS(int, webio_js_audio_play, (const char *path, int volume), {
    var H = Module.__webio;
    if (!H || !H.audio || H.audio.context.state !== "running") return 0;
    var A = H.audio;
    var generation = ++A.generation;
    if (A.source) {
        try { A.source.stop(); } catch (e) {}
        A.source = null;
    }
    var bytes;
    try {
        bytes = FS.readFile(UTF8ToString(path));
    } catch (e) {
        console.error("Web audio read failed:", e);
        return 0;
    }

    function startBuffer(buffer) {
        if (generation !== A.generation) return;
        var source = A.context.createBufferSource();
        var gain = A.context.createGain();
        gain.gain.value = Math.max(0, Math.min(1, volume / 100));
        source.buffer = buffer;
        source.connect(gain);
        gain.connect(A.context.destination);
        source.onended = function() {
            if (A.source === source) {
                A.source = null;
                A.sourceGain = null;
            }
        };
        A.source = source;
        A.sourceGain = gain;
        source.start();
    }

    function decodeWav(data) {
        var view = new DataView(data.buffer, data.byteOffset, data.byteLength);
        function tag(offset) {
            return String.fromCharCode(
                view.getUint8(offset), view.getUint8(offset + 1),
                view.getUint8(offset + 2), view.getUint8(offset + 3)
            );
        }
        if (tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("not a WAV file");
        var format = 0;
        var channels = 0;
        var sampleRate = 0;
        var blockAlign = 0;
        var bits = 0;
        var dataOffset = 0;
        var dataSize = 0;
        var factSamples = 0;
        var pos = 12;
        while (pos + 8 <= view.byteLength) {
            var id = tag(pos);
            var size = view.getUint32(pos + 4, true);
            var start = pos + 8;
            if (id === "fmt " && size >= 16) {
                format = view.getUint16(start, true);
                channels = view.getUint16(start + 2, true);
                sampleRate = view.getUint32(start + 4, true);
                blockAlign = view.getUint16(start + 12, true);
                bits = view.getUint16(start + 14, true);
                if (format === 0xfffe && size >= 26) format = view.getUint16(start + 24, true);
            } else if (id === "fact" && size >= 4) {
                factSamples = view.getUint32(start, true);
            } else if (id === "data") {
                dataOffset = start;
                dataSize = Math.min(size, view.byteLength - start);
            }
            pos = start + size + (size & 1);
        }
        if (!channels || !sampleRate || !dataOffset || !dataSize) throw new Error("invalid WAV header");

        if (format === 1) {
            var bytesPerSample = bits >> 3;
            var frames = Math.floor(dataSize / (channels * bytesPerSample));
            var pcmBuffer = A.context.createBuffer(channels, frames, sampleRate);
            var pcmChannels = [];
            for (var c = 0; c < channels; c++) pcmChannels.push(pcmBuffer.getChannelData(c));
            var offset = dataOffset;
            for (var frame = 0; frame < frames; frame++) {
                for (var channel = 0; channel < channels; channel++) {
                    var sample;
                    if (bits === 8) {
                        sample = (view.getUint8(offset) - 128) / 128;
                    } else if (bits === 16) {
                        sample = view.getInt16(offset, true) / 32768;
                    } else if (bits === 24) {
                        var raw = view.getUint8(offset) | (view.getUint8(offset + 1) << 8) |
                            (view.getUint8(offset + 2) << 16);
                        if (raw & 0x800000) raw |= 0xff000000;
                        sample = raw / 8388608;
                    } else if (bits === 32) {
                        sample = view.getInt32(offset, true) / 2147483648;
                    } else {
                        throw new Error("unsupported PCM depth " + bits);
                    }
                    pcmChannels[channel][frame] = sample;
                    offset += bytesPerSample;
                }
            }
            return pcmBuffer;
        }

        if (format === 0x11) {
            var steps = [
                7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,66,
                73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,
                449,494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,
                2066,2272,2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,
                7845,8630,9493,10442,11487,12635,13900,15289,16818,18500,20350,22385,
                24623,27086,29794,32767
            ];
            var indexes = [-1,-1,-1,-1,2,4,6,8,-1,-1,-1,-1,2,4,6,8];
            var samplesPerBlock = 1 + Math.floor((blockAlign - 4 * channels) * 2 / channels);
            var blockCount = Math.floor(dataSize / blockAlign);
            var totalFrames = factSamples || blockCount * samplesPerBlock;
            var adpcmBuffer = A.context.createBuffer(channels, totalFrames, sampleRate);
            var adpcmChannels = [];
            for (var ac = 0; ac < channels; ac++) adpcmChannels.push(adpcmBuffer.getChannelData(ac));
            var blockOffset = dataOffset;
            var frameBase = 0;
            for (var block = 0; block < blockCount && frameBase < totalFrames; block++) {
                var predictors = [];
                var stepIndexes = [];
                var writePositions = [];
                for (var headerChannel = 0; headerChannel < channels; headerChannel++) {
                    var header = blockOffset + headerChannel * 4;
                    predictors[headerChannel] = view.getInt16(header, true);
                    stepIndexes[headerChannel] = Math.max(0, Math.min(88, view.getUint8(header + 2)));
                    adpcmChannels[headerChannel][frameBase] = predictors[headerChannel] / 32768;
                    writePositions[headerChannel] = frameBase + 1;
                }
                var encodedPos = blockOffset + 4 * channels;
                var blockEnd = blockOffset + blockAlign;
                while (encodedPos + 4 * channels <= blockEnd) {
                    for (var encodedChannel = 0; encodedChannel < channels; encodedChannel++) {
                        for (var byteIndex = 0; byteIndex < 4; byteIndex++) {
                            var encodedByte = view.getUint8(encodedPos++);
                            for (var half = 0; half < 2; half++) {
                                var nibble = half ? encodedByte >> 4 : encodedByte & 15;
                                var step = steps[stepIndexes[encodedChannel]];
                                var diff = (((nibble & 7) * 2 + 1) * step) >> 3;
                                predictors[encodedChannel] += (nibble & 8) ? -diff : diff;
                                predictors[encodedChannel] = Math.max(-32768, Math.min(32767, predictors[encodedChannel]));
                                stepIndexes[encodedChannel] = Math.max(
                                    0, Math.min(88, stepIndexes[encodedChannel] + indexes[nibble])
                                );
                                if (writePositions[encodedChannel] < totalFrames) {
                                    adpcmChannels[encodedChannel][writePositions[encodedChannel]++] =
                                        predictors[encodedChannel] / 32768;
                                }
                            }
                        }
                    }
                }
                frameBase += samplesPerBlock;
                blockOffset += blockAlign;
            }
            return adpcmBuffer;
        }

        throw new Error("unsupported WAV format " + format);
    }

    try {
        startBuffer(decodeWav(bytes));
    } catch (wavError) {
        var encoded = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
        A.context.decodeAudioData(encoded).then(startBuffer).catch(function(e) {
            console.error("Web audio decode failed:", wavError, e);
        });
    }
    return 1;
});

EM_JS(void, webio_js_audio_stop, (void), {
    var H = Module.__webio;
    if (!H || !H.audio) return;
    var A = H.audio;
    ++A.generation;
    if (A.source) {
        try { A.source.stop(); } catch (e) {}
        A.source = null;
        A.sourceGain = null;
    }
});

EM_JS(void, webio_js_audio_volume, (int volume), {
    var H = Module.__webio;
    if (!H || !H.audio || !H.audio.sourceGain) return;
    H.audio.sourceGain.gain.setValueAtTime(
        Math.max(0, Math.min(1, volume / 100)),
        H.audio.context.currentTime
    );
});

// ---------------------------------------------------------------------------
// MicroPython bindings
// ---------------------------------------------------------------------------

// init() -> None  (ensure Module.__webio.{buttons,joy_x,joy_y,onLeds} exist)
static mp_obj_t webio_init(void) {
    webio_js_init();
    webio_js_audio_init();
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

static mp_obj_t webio_tone(mp_obj_t frequency_in, mp_obj_t duty_in) {
    webio_js_audio_init();
    webio_js_tone(mp_obj_get_int(frequency_in), mp_obj_get_int(duty_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(webio_tone_obj, webio_tone);

static mp_obj_t webio_tone_stop(void) {
    webio_js_tone_stop();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(webio_tone_stop_obj, webio_tone_stop);

static mp_obj_t webio_audio_play(mp_obj_t path_in, mp_obj_t volume_in) {
    webio_js_audio_init();
    return mp_obj_new_bool(webio_js_audio_play(
        mp_obj_str_get_str(path_in), mp_obj_get_int(volume_in)
    ));
}
static MP_DEFINE_CONST_FUN_OBJ_2(webio_audio_play_obj, webio_audio_play);

static mp_obj_t webio_audio_stop(void) {
    webio_js_audio_stop();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(webio_audio_stop_obj, webio_audio_stop);

static mp_obj_t webio_audio_volume(mp_obj_t volume_in) {
    webio_js_audio_volume(mp_obj_get_int(volume_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webio_audio_volume_obj, webio_audio_volume);

static const mp_rom_map_elem_t webio_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__webio) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&webio_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_leds_write), MP_ROM_PTR(&webio_leds_write_obj) },
    { MP_ROM_QSTR(MP_QSTR_buttons), MP_ROM_PTR(&webio_buttons_obj) },
    { MP_ROM_QSTR(MP_QSTR_joystick), MP_ROM_PTR(&webio_joystick_obj) },
    { MP_ROM_QSTR(MP_QSTR_tone), MP_ROM_PTR(&webio_tone_obj) },
    { MP_ROM_QSTR(MP_QSTR_tone_stop), MP_ROM_PTR(&webio_tone_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_audio_play), MP_ROM_PTR(&webio_audio_play_obj) },
    { MP_ROM_QSTR(MP_QSTR_audio_stop), MP_ROM_PTR(&webio_audio_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_audio_volume), MP_ROM_PTR(&webio_audio_volume_obj) },
};
static MP_DEFINE_CONST_DICT(webio_module_globals, webio_module_globals_table);

const mp_obj_module_t webio_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&webio_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__webio, webio_user_cmodule);

#endif // __EMSCRIPTEN__
