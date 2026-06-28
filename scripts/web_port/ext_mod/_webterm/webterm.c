// _webterm — browser terminal (stdio) bridge for the MicroPythonOS WebAssembly
// build.
//
// Exposes a tiny, NON-BLOCKING byte pipe between the browser/JS host and
// MicroPython so an external host (e.g. ViperIDE / Fri3d-IDE) can drive the
// MicroPythonOS asyncio REPL like a serial device, even though the browser has
// no readable stdin.
//
// Direction host -> Python (input):
//   The JS host pushes incoming bytes into Module.__webterm.inq (an array of
//   byte values). Python drains it with rx()/any().
//
// Direction Python -> host (output):
//   Python calls tx(bytes); the bytes are handed to Module.__webterm.onOutput
//   (a JS callback the host installs) as a Uint8Array. REPL output (mirrored
//   from sys.stdout via os.dupterm) flows out this way.
//
// This file is only compiled for the Emscripten/web target (guarded by
// __EMSCRIPTEN__ and gated to MPOS_WEB=1 in micropython.mk); on every other
// port it compiles to nothing.

#include <stdlib.h>

#include "py/runtime.h"
#include "py/obj.h"
#include "py/mperrno.h"

#if defined(__EMSCRIPTEN__)

#include <emscripten.h>

// ---------------------------------------------------------------------------
// JS side: Module.__webterm = { inq: [byte, ...], onOutput: fn(Uint8Array) }.
// The host installs onOutput and pushes input bytes onto inq. A convenience
// push() helper is attached so the host can feed a Uint8Array/array of bytes.
// ---------------------------------------------------------------------------

EM_JS(void, webterm_js_init, (void), {
    var H = Module.__webterm || (Module.__webterm = {});
    if (!H.inq) { H.inq = []; }
    if (!H.onOutput) { H.onOutput = null; }
    if (!H.push) {
        // Accepts a Uint8Array, Array, or single byte number.
        H.push = function (data) {
            if (typeof data === "number") { H.inq.push(data & 0xff); return; }
            for (var i = 0; i < data.length; i++) { H.inq.push(data[i] & 0xff); }
        };
    }
});

EM_JS(int, webterm_js_rx, (void), {
    var H = Module.__webterm; if (!H || !H.inq || !H.inq.length) return -1;
    return H.inq.shift() & 0xff;
});

EM_JS(int, webterm_js_any, (void), {
    var H = Module.__webterm; if (!H || !H.inq) return 0;
    return H.inq.length;
});

EM_JS(void, webterm_js_tx, (const char *buf, int len), {
    var H = Module.__webterm; if (!H || typeof H.onOutput !== "function") return;
    // Copy the bytes out of the wasm heap before handing them to JS (the heap
    // may move/grow), then deliver a fresh Uint8Array to the host callback.
    try { H.onOutput(HEAPU8.slice(buf, buf + len)); } catch (e) {}
});

// ---------------------------------------------------------------------------
// Global stdout hook. unix_mphal.c (patched for the web build) calls this from
// mp_hal_stdout_tx_strn so that ALL MicroPython stdout — boot logs, REPL
// framing, and the output of code executed over the REPL — is mirrored to the
// JS host. webterm_js_tx() no-ops when no host onOutput callback is installed,
// so this is inert until a host (e.g. ViperIDE) attaches.
// ---------------------------------------------------------------------------

void mp_webterm_stdout(const char *str, size_t len) {
    if (len > 0) {
        webterm_js_tx(str, (int)len);
    }
}

// ---------------------------------------------------------------------------
// MicroPython bindings
// ---------------------------------------------------------------------------

// init() -> None  (ensure Module.__webterm.{inq,onOutput,push} exist)
static mp_obj_t webterm_init(void) {
    webterm_js_init();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(webterm_init_obj, webterm_init);

// rx() -> int  (next input byte 0..255, or -1 if the queue is empty)
static mp_obj_t webterm_rx(void) {
    return mp_obj_new_int(webterm_js_rx());
}
static MP_DEFINE_CONST_FUN_OBJ_0(webterm_rx_obj, webterm_rx);

// any() -> int  (number of bytes currently queued for input)
static mp_obj_t webterm_any(void) {
    return mp_obj_new_int(webterm_js_any());
}
static MP_DEFINE_CONST_FUN_OBJ_0(webterm_any_obj, webterm_any);

// tx(data:bytes) -> None  (deliver output bytes to the host onOutput callback)
static mp_obj_t webterm_tx(mp_obj_t data_in) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_in, &bufinfo, MP_BUFFER_READ);
    if (bufinfo.len > 0) {
        webterm_js_tx((const char *)bufinfo.buf, (int)bufinfo.len);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webterm_tx_obj, webterm_tx);

static const mp_rom_map_elem_t webterm_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__webterm) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&webterm_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_rx), MP_ROM_PTR(&webterm_rx_obj) },
    { MP_ROM_QSTR(MP_QSTR_any), MP_ROM_PTR(&webterm_any_obj) },
    { MP_ROM_QSTR(MP_QSTR_tx), MP_ROM_PTR(&webterm_tx_obj) },
};
static MP_DEFINE_CONST_DICT(webterm_module_globals, webterm_module_globals_table);

const mp_obj_module_t webterm_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&webterm_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__webterm, webterm_user_cmodule);

#endif // __EMSCRIPTEN__
