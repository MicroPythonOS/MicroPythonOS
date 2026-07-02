// _webnet — browser networking bridge for the MicroPythonOS WebAssembly build.
//
// Exposes the browser fetch() API to MicroPython as a small, NON-BLOCKING,
// poll-based module so HTTP(S) works in the browser (where raw TCP sockets are
// unavailable and MICROPY_PY_SOCKET is disabled).
//
// Design: fetch_start() kicks off a fetch() and returns immediately with an
// integer handle; the request runs on the browser event loop. Python then
// polls poll(handle) (yielding to the asyncio loop via asyncio.sleep between
// polls) so the LVGL/UI task handler keeps running during downloads. When the
// body has fully arrived, status()/headers()/body() return the result.
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
// JS side: a per-handle record { state, status, headers, body, err } kept on
// Module.__webnet.map. state: 0 = pending, 1 = done, -1 = error.
// ---------------------------------------------------------------------------

EM_JS(int, webnet_js_start,
      (const char *method, const char *url, const char *headers_json,
       const char *body, int body_len), {
    var H = Module.__webnet || (Module.__webnet = { next: 1, map: {} });
    var handle = H.next++;
    var rec = { state: 0, status: 0, headers: "{}", body: null, err: "" };
    H.map[handle] = rec;
    try {
        var m = UTF8ToString(method);
        var u = UTF8ToString(url);
        var hs = UTF8ToString(headers_json);
        var hdrs = {};
        try { hdrs = JSON.parse(hs); } catch (e) {}
        var opts = { method: m, headers: hdrs };
        if (body_len > 0) {
            // Copy the request body out of the wasm heap before it can move.
            opts.body = HEAPU8.slice(body, body + body_len);
        }
        fetch(u, opts).then(function (resp) {
            rec.status = resp.status;
            var ho = {};
            resp.headers.forEach(function (v, k) { ho[k] = v; });
            rec.headers = JSON.stringify(ho);
            return resp.arrayBuffer();
        }).then(function (ab) {
            rec.body = new Uint8Array(ab);
            rec.state = 1;
        }).catch(function (e) {
            rec.err = "" + e;
            rec.state = -1;
        });
    } catch (e) {
        rec.err = "" + e;
        rec.state = -1;
    }
    return handle;
});

EM_JS(int, webnet_js_poll, (int handle), {
    var H = Module.__webnet; if (!H) return -1;
    var rec = H.map[handle]; if (!rec) return -1;
    return rec.state;
});

EM_JS(int, webnet_js_status, (int handle), {
    var H = Module.__webnet; if (!H) return 0;
    var rec = H.map[handle]; if (!rec) return 0;
    return rec.status;
});

EM_JS(int, webnet_js_headers_len, (int handle), {
    var H = Module.__webnet; if (!H) return 0;
    var rec = H.map[handle]; if (!rec) return 0;
    return lengthBytesUTF8(rec.headers);
});

EM_JS(void, webnet_js_headers_copy, (int handle, char *buf, int len), {
    var H = Module.__webnet; if (!H) return;
    var rec = H.map[handle]; if (!rec) return;
    stringToUTF8(rec.headers, buf, len + 1);
});

EM_JS(int, webnet_js_error_len, (int handle), {
    var H = Module.__webnet; if (!H) return 0;
    var rec = H.map[handle]; if (!rec) return 0;
    return lengthBytesUTF8(rec.err);
});

EM_JS(void, webnet_js_error_copy, (int handle, char *buf, int len), {
    var H = Module.__webnet; if (!H) return;
    var rec = H.map[handle]; if (!rec) return;
    stringToUTF8(rec.err, buf, len + 1);
});

EM_JS(int, webnet_js_body_len, (int handle), {
    var H = Module.__webnet; if (!H) return 0;
    var rec = H.map[handle]; if (!rec || !rec.body) return 0;
    return rec.body.length;
});

EM_JS(void, webnet_js_body_copy, (int handle, char *buf, int len), {
    var H = Module.__webnet; if (!H) return;
    var rec = H.map[handle]; if (!rec || !rec.body) return;
    HEAPU8.set(rec.body.subarray(0, len), buf);
});

EM_JS(void, webnet_js_free, (int handle), {
    var H = Module.__webnet; if (!H) return;
    delete H.map[handle];
});

// ---------------------------------------------------------------------------
// JS side: WebSocket bridge. Shares Module.__webnet.map / next with fetch, but
// uses a different record shape { ws, queue, err, enc }. Incoming messages are
// queued (text encoded to UTF-8 bytes, binary as Uint8Array) and drained by
// Python via ws_peek_type/ws_peek_len/ws_read. State mirrors WebSocket
// .readyState (0 CONNECTING, 1 OPEN, 2 CLOSING, 3 CLOSED).
//
// Note: the browser WebSocket API cannot set custom request headers and is not
// subject to CORS the way fetch() is (the server decides via the Origin
// header), so cross-origin relays generally work.
// ---------------------------------------------------------------------------

EM_JS(int, webnet_js_ws_open, (const char *url, const char *protocols_json), {
    var H = Module.__webnet || (Module.__webnet = { next: 1, map: {} });
    var handle = H.next++;
    var rec = { ws: null, queue: [], err: "", enc: null };
    H.map[handle] = rec;
    try {
        var u = UTF8ToString(url);
        var ps = UTF8ToString(protocols_json);
        var protocols = [];
        try { protocols = JSON.parse(ps); } catch (e) {}
        var ws = (protocols && protocols.length)
            ? new WebSocket(u, protocols)
            : new WebSocket(u);
        ws.binaryType = "arraybuffer";
        rec.ws = ws;
        rec.enc = (typeof TextEncoder !== "undefined") ? new TextEncoder() : null;
        ws.onmessage = function (ev) {
            var d = ev.data;
            if (typeof d === "string") {
                var bytes = rec.enc ? rec.enc.encode(d) : new Uint8Array(0);
                rec.queue.push({ type: 1, data: bytes });
            } else {
                rec.queue.push({ type: 2, data: new Uint8Array(d) });
            }
        };
        ws.onerror = function (ev) { rec.err = "websocket error"; };
    } catch (e) {
        rec.err = "" + e;
    }
    return handle;
});

EM_JS(int, webnet_js_ws_state, (int handle), {
    var H = Module.__webnet; if (!H) return 3;
    var rec = H.map[handle]; if (!rec || !rec.ws) return 3;
    return rec.ws.readyState;
});

EM_JS(int, webnet_js_ws_peek_type, (int handle), {
    var H = Module.__webnet; if (!H) return 0;
    var rec = H.map[handle]; if (!rec || !rec.queue.length) return 0;
    return rec.queue[0].type;
});

EM_JS(int, webnet_js_ws_peek_len, (int handle), {
    var H = Module.__webnet; if (!H) return 0;
    var rec = H.map[handle]; if (!rec || !rec.queue.length) return 0;
    return rec.queue[0].data.length;
});

EM_JS(void, webnet_js_ws_read_copy, (int handle, char *buf, int len), {
    var H = Module.__webnet; if (!H) return;
    var rec = H.map[handle]; if (!rec || !rec.queue.length) return;
    var msg = rec.queue.shift();
    if (len > 0) { HEAPU8.set(msg.data.subarray(0, len), buf); }
});

EM_JS(int, webnet_js_ws_send_text, (int handle, const char *str), {
    var H = Module.__webnet; if (!H) return -1;
    var rec = H.map[handle]; if (!rec || !rec.ws) return -1;
    try { rec.ws.send(UTF8ToString(str)); return 0; }
    catch (e) { rec.err = "" + e; return -1; }
});

EM_JS(int, webnet_js_ws_send_bytes, (int handle, const char *buf, int len), {
    var H = Module.__webnet; if (!H) return -1;
    var rec = H.map[handle]; if (!rec || !rec.ws) return -1;
    try { rec.ws.send(HEAPU8.slice(buf, buf + len)); return 0; }
    catch (e) { rec.err = "" + e; return -1; }
});

EM_JS(void, webnet_js_ws_close, (int handle), {
    var H = Module.__webnet; if (!H) return;
    var rec = H.map[handle]; if (!rec || !rec.ws) return;
    try { rec.ws.close(); } catch (e) {}
});

EM_JS(int, webnet_js_ws_error_len, (int handle), {
    var H = Module.__webnet; if (!H) return 0;
    var rec = H.map[handle]; if (!rec) return 0;
    return lengthBytesUTF8(rec.err);
});

EM_JS(void, webnet_js_ws_error_copy, (int handle, char *buf, int len), {
    var H = Module.__webnet; if (!H) return;
    var rec = H.map[handle]; if (!rec) return;
    stringToUTF8(rec.err, buf, len + 1);
});

EM_JS(void, webnet_js_ws_free, (int handle), {
    var H = Module.__webnet; if (!H) return;
    var rec = H.map[handle];
    if (rec && rec.ws) { try { rec.ws.close(); } catch (e) {} }
    delete H.map[handle];
});

// ---------------------------------------------------------------------------
// MicroPython bindings
// ---------------------------------------------------------------------------

// fetch_start(method:str, url:str, headers_json:str, body:bytes|None) -> int
static mp_obj_t webnet_fetch_start(size_t n_args, const mp_obj_t *args) {
    const char *method = mp_obj_str_get_str(args[0]);
    const char *url = mp_obj_str_get_str(args[1]);
    const char *headers = mp_obj_str_get_str(args[2]);
    const char *body = NULL;
    int body_len = 0;
    if (n_args > 3 && args[3] != mp_const_none) {
        mp_buffer_info_t bufinfo;
        mp_get_buffer_raise(args[3], &bufinfo, MP_BUFFER_READ);
        body = (const char *)bufinfo.buf;
        body_len = (int)bufinfo.len;
    }
    return mp_obj_new_int(webnet_js_start(method, url, headers, body, body_len));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(webnet_fetch_start_obj, 3, 4, webnet_fetch_start);

// poll(handle:int) -> int  (0 pending, 1 done, -1 error)
static mp_obj_t webnet_poll(mp_obj_t handle_in) {
    return mp_obj_new_int(webnet_js_poll(mp_obj_get_int(handle_in)));
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_poll_obj, webnet_poll);

// status(handle:int) -> int
static mp_obj_t webnet_status(mp_obj_t handle_in) {
    return mp_obj_new_int(webnet_js_status(mp_obj_get_int(handle_in)));
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_status_obj, webnet_status);

// headers(handle:int) -> str  (JSON object of response headers)
static mp_obj_t webnet_headers(mp_obj_t handle_in) {
    int handle = mp_obj_get_int(handle_in);
    int len = webnet_js_headers_len(handle);
    if (len <= 0) {
        return mp_obj_new_str("{}", 2);
    }
    char *buf = malloc((size_t)len + 1);
    if (buf == NULL) {
        mp_raise_OSError(MP_ENOMEM);
    }
    webnet_js_headers_copy(handle, buf, len);
    buf[len] = '\0';
    mp_obj_t result = mp_obj_new_str(buf, len);
    free(buf);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_headers_obj, webnet_headers);

// error(handle:int) -> str
static mp_obj_t webnet_error(mp_obj_t handle_in) {
    int handle = mp_obj_get_int(handle_in);
    int len = webnet_js_error_len(handle);
    if (len <= 0) {
        return mp_obj_new_str("", 0);
    }
    char *buf = malloc((size_t)len + 1);
    if (buf == NULL) {
        mp_raise_OSError(MP_ENOMEM);
    }
    webnet_js_error_copy(handle, buf, len);
    buf[len] = '\0';
    mp_obj_t result = mp_obj_new_str(buf, len);
    free(buf);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_error_obj, webnet_error);

// body(handle:int) -> bytes  (full response body)
static mp_obj_t webnet_body(mp_obj_t handle_in) {
    int handle = mp_obj_get_int(handle_in);
    int len = webnet_js_body_len(handle);
    if (len <= 0) {
        return mp_obj_new_bytes((const byte *)"", 0);
    }
    char *buf = malloc((size_t)len);
    if (buf == NULL) {
        mp_raise_OSError(MP_ENOMEM);
    }
    webnet_js_body_copy(handle, buf, len);
    mp_obj_t result = mp_obj_new_bytes((const byte *)buf, len);
    free(buf);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_body_obj, webnet_body);

// free(handle:int) -> None
static mp_obj_t webnet_free(mp_obj_t handle_in) {
    webnet_js_free(mp_obj_get_int(handle_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_free_obj, webnet_free);

// --- WebSocket bindings ----------------------------------------------------

// ws_open(url:str, protocols_json:str) -> int  (handle)
static mp_obj_t webnet_ws_open(mp_obj_t url_in, mp_obj_t protocols_in) {
    const char *url = mp_obj_str_get_str(url_in);
    const char *protocols = mp_obj_str_get_str(protocols_in);
    return mp_obj_new_int(webnet_js_ws_open(url, protocols));
}
static MP_DEFINE_CONST_FUN_OBJ_2(webnet_ws_open_obj, webnet_ws_open);

// ws_state(handle:int) -> int  (0 connecting, 1 open, 2 closing, 3 closed)
static mp_obj_t webnet_ws_state(mp_obj_t handle_in) {
    return mp_obj_new_int(webnet_js_ws_state(mp_obj_get_int(handle_in)));
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_ws_state_obj, webnet_ws_state);

// ws_peek_type(handle:int) -> int  (0 none, 1 text, 2 binary)
static mp_obj_t webnet_ws_peek_type(mp_obj_t handle_in) {
    return mp_obj_new_int(webnet_js_ws_peek_type(mp_obj_get_int(handle_in)));
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_ws_peek_type_obj, webnet_ws_peek_type);

// ws_peek_len(handle:int) -> int  (byte length of the queued front message)
static mp_obj_t webnet_ws_peek_len(mp_obj_t handle_in) {
    return mp_obj_new_int(webnet_js_ws_peek_len(mp_obj_get_int(handle_in)));
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_ws_peek_len_obj, webnet_ws_peek_len);

// ws_read(handle:int) -> bytes  (pops and returns the front message payload)
static mp_obj_t webnet_ws_read(mp_obj_t handle_in) {
    int handle = mp_obj_get_int(handle_in);
    int len = webnet_js_ws_peek_len(handle);
    if (len < 0) {
        len = 0;
    }
    char *buf = malloc((size_t)len + 1);  // +1 avoids malloc(0)
    if (buf == NULL) {
        mp_raise_OSError(MP_ENOMEM);
    }
    webnet_js_ws_read_copy(handle, buf, len);  // pops the front message
    mp_obj_t result = mp_obj_new_bytes((const byte *)buf, len);
    free(buf);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_ws_read_obj, webnet_ws_read);

// ws_send_text(handle:int, data:str) -> int  (0 ok, -1 error)
static mp_obj_t webnet_ws_send_text(mp_obj_t handle_in, mp_obj_t data_in) {
    return mp_obj_new_int(
        webnet_js_ws_send_text(mp_obj_get_int(handle_in), mp_obj_str_get_str(data_in)));
}
static MP_DEFINE_CONST_FUN_OBJ_2(webnet_ws_send_text_obj, webnet_ws_send_text);

// ws_send_bytes(handle:int, data:bytes) -> int  (0 ok, -1 error)
static mp_obj_t webnet_ws_send_bytes(mp_obj_t handle_in, mp_obj_t data_in) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(data_in, &bufinfo, MP_BUFFER_READ);
    return mp_obj_new_int(
        webnet_js_ws_send_bytes(mp_obj_get_int(handle_in),
                                (const char *)bufinfo.buf, (int)bufinfo.len));
}
static MP_DEFINE_CONST_FUN_OBJ_2(webnet_ws_send_bytes_obj, webnet_ws_send_bytes);

// ws_close(handle:int) -> None
static mp_obj_t webnet_ws_close(mp_obj_t handle_in) {
    webnet_js_ws_close(mp_obj_get_int(handle_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_ws_close_obj, webnet_ws_close);

// ws_error(handle:int) -> str
static mp_obj_t webnet_ws_error(mp_obj_t handle_in) {
    int handle = mp_obj_get_int(handle_in);
    int len = webnet_js_ws_error_len(handle);
    if (len <= 0) {
        return mp_obj_new_str("", 0);
    }
    char *buf = malloc((size_t)len + 1);
    if (buf == NULL) {
        mp_raise_OSError(MP_ENOMEM);
    }
    webnet_js_ws_error_copy(handle, buf, len);
    buf[len] = '\0';
    mp_obj_t result = mp_obj_new_str(buf, len);
    free(buf);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_ws_error_obj, webnet_ws_error);

// ws_free(handle:int) -> None
static mp_obj_t webnet_ws_free(mp_obj_t handle_in) {
    webnet_js_ws_free(mp_obj_get_int(handle_in));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webnet_ws_free_obj, webnet_ws_free);

static const mp_rom_map_elem_t webnet_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__webnet) },
    { MP_ROM_QSTR(MP_QSTR_fetch_start), MP_ROM_PTR(&webnet_fetch_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_poll), MP_ROM_PTR(&webnet_poll_obj) },
    { MP_ROM_QSTR(MP_QSTR_status), MP_ROM_PTR(&webnet_status_obj) },
    { MP_ROM_QSTR(MP_QSTR_headers), MP_ROM_PTR(&webnet_headers_obj) },
    { MP_ROM_QSTR(MP_QSTR_error), MP_ROM_PTR(&webnet_error_obj) },
    { MP_ROM_QSTR(MP_QSTR_body), MP_ROM_PTR(&webnet_body_obj) },
    { MP_ROM_QSTR(MP_QSTR_free), MP_ROM_PTR(&webnet_free_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_open), MP_ROM_PTR(&webnet_ws_open_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_state), MP_ROM_PTR(&webnet_ws_state_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_peek_type), MP_ROM_PTR(&webnet_ws_peek_type_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_peek_len), MP_ROM_PTR(&webnet_ws_peek_len_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_read), MP_ROM_PTR(&webnet_ws_read_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_send_text), MP_ROM_PTR(&webnet_ws_send_text_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_send_bytes), MP_ROM_PTR(&webnet_ws_send_bytes_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_close), MP_ROM_PTR(&webnet_ws_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_error), MP_ROM_PTR(&webnet_ws_error_obj) },
    { MP_ROM_QSTR(MP_QSTR_ws_free), MP_ROM_PTR(&webnet_ws_free_obj) },
};
static MP_DEFINE_CONST_DICT(webnet_module_globals, webnet_module_globals_table);

const mp_obj_module_t webnet_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&webnet_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__webnet, webnet_user_cmodule);

#endif // __EMSCRIPTEN__
