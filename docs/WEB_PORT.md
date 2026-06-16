# MicroPythonOS Web (WebAssembly / Emscripten) Port

This document describes how MicroPythonOS runs in the browser, how to build and
serve it, and everything you need to know to make changes. **The entire web port
is self-contained in this (`MicroPythonOS`) repository** — no edits to the
`lvgl_micropython` submodule (or its nested `micropython`/`lvgl`) need to be
committed. The submodule modifications required by the web target are stored
here as patches/files under [`scripts/web_port/`](../scripts/web_port/) and are
applied automatically at build time.

---

## TL;DR

```bash
# 1. One-time: install & activate the Emscripten SDK (see "Prerequisites").
#    The build auto-activates ../emsdk or ../../emsdk if emcc is not on PATH.

# 2. Build the web target.
scripts/build_mpos_web.sh

# 3. Build (if needed) and serve locally at http://localhost:8080/
scripts/run_web.sh
#   scripts/run_web.sh --no-build   # serve existing web/ without rebuilding
#   PORT=9000 scripts/run_web.sh     # serve on a different port
```

Output artifacts land in [`web/`](../web/): `micropython.{html,js,wasm,data}`,
plus copies `index.html` and `mpos.html`.

---

## Prerequisites

- **Emscripten SDK** (tested with **6.0.0**). Either have `emcc` on `PATH`, or
  place an activated `emsdk` checkout one or two directories above this repo
  (`../emsdk` or `../../emsdk`). `scripts/build_mpos_web.sh` sources
  `emsdk_env.sh` automatically when `emcc` is missing.
- Standard host toolchain to build `mpy-cross` (built with the host compiler,
  not emcc) and the usual MicroPython build dependencies (`python3`, `make`).
- The git submodules must be checked out (`git submodule update --init
  --recursive`). A **clean** submodule checkout is fine — the build re-applies
  the web changes every time.

---

## Build from a fresh clone (sharing / forking)

The entire web port lives in this repository, so a fork is self-contained: a
fresh clone plus the submodules plus an Emscripten SDK is all that is needed.
The submodule C changes are re-applied automatically by the build, so **nothing
needs to be committed into any submodule.**

```bash
# 1. Clone your fork with submodules.
git clone --recursive https://github.com/<you>/MicroPythonOS
cd MicroPythonOS
#   (if you forgot --recursive:)
#   git submodule update --init --recursive

# 2. Install + activate Emscripten 6.0.0 somewhere the build can find it
#    (emcc on PATH, or an activated emsdk at ../emsdk or ../../emsdk).

# 3. Build and serve.
scripts/build_mpos_web.sh
scripts/run_web.sh
```

### Pinned submodule commits (known-good)

The two C patches apply against specific upstream revisions. If a submodule is
advanced past these, `patch --forward` may reject a hunk (the build logs the
failure but continues, so a broken boot can result). These are the commits this
port was verified against:

| Submodule | Commit | Tag/branch |
| --- | --- | --- |
| `lvgl_micropython` | `a491b2a` | `integration` |
| `lvgl_micropython/lib/micropython` | `78ff170` | `v1.27.0` |
| `lvgl_micropython/lib/lvgl` | `c016f72` | `v9.3.0-556` |
| `lvgl_micropython/lib/SDL` | `6ad390fc` | `release-2.26.0-4202` |
| `freezeFS` | `5f211e3` | `main` |
| `secp256k1-embedded-ecdh` | `f86eb16` | `micropython_1.25.0` |
| `micropython-camera-API` | `f88b29d` | `master` |
| `micropython-nostr` | `2375c45` | `0.9-22` |

The critical two for the web patches are `lvgl_micropython` (for
`sdl_bus.h`) and `lvgl_micropython/lib/micropython` (for `gccollect.c`). A fork
should pin at least those. If you bump them, regenerate the patches (see
*Updating a submodule patch*) and re-verify a clean boot.

---

## How it works (architecture)

The web target reuses the **unix port** of MicroPython (LVGL + SDL display/input
drivers, the frozen manifest, the `ext_mod` C modules) but compiles it with the
Emscripten toolchain (`emcc`/`em++`/`emar`) and links Emscripten's bundled SDL2
port (`-sUSE_SDL=2`) instead of a natively built `libSDL2.a`. The result renders
into an HTML `<canvas>`.

```
┌─────────────────────────────────────────────────────────────┐
│ Browser tab (web/mpos.html → micropython.js + .wasm + .data) │
│                                                              │
│   <canvas>  ◀── SDL2 (Emscripten port) ◀── LVGL ◀── MPOS     │
│                                                              │
│   asyncio event loop (TaskManager.start → asyncio.run)       │
│     ├─ task_handler  (drives lv.task_handler + lv.tick_inc)  │
│     └─ machine.Timer  (asyncio-backed periodic/one-shot)     │
└─────────────────────────────────────────────────────────────┘
```

Key design points:

- **`REAL_PORT = 'unix'`** — all unix patches and `machine_sdl` reuse unchanged.
- **No native threads / sockets / ffi / termios / bluetooth.** The web build
  sets `MICROPY_PY_THREAD/SOCKET/FFI/TERMIOS/BLUETOOTH=0`. Python modules that
  expect those are satisfied with small web-only shims (see below).
- **No native `machine.Timer`.** `machine_timer.c` is dropped from the web
  Makefile; an asyncio-backed `Timer` is injected at boot.
- **The preloaded filesystem is mounted at `/`** (root), matching the on-device
  layout, because `main.py` does `sys.path.insert(0, "lib")` and apps use
  root-relative paths like `/apps` and `/builtin`.

---

## Where everything lives (all in this repo)

| Path | Purpose |
| --- | --- |
| [`scripts/build_mpos.sh`](../scripts/build_mpos.sh) | Central build orchestration. The `web` target branch does all web-specific work (patching the submodule, staging the FS, injecting shims, invoking `make.py web`, collecting artifacts). |
| [`scripts/build_mpos_web.sh`](../scripts/build_mpos_web.sh) | Convenience wrapper: activates emsdk then runs `build_mpos.sh web`. |
| [`scripts/run_web.sh`](../scripts/run_web.sh) | Build (optional) + serve `web/` with `python3 -m http.server`. |
| [`scripts/web_port/web.py`](../scripts/web_port/web.py) | The Emscripten build backend. Copied into `lvgl_micropython/builder/web.py` at build time; consumed by `make.py web`. |
| [`scripts/web_port/sdl_bus.h.patch`](../scripts/web_port/sdl_bus.h.patch) | C struct-layout fix applied to the `lcd_bus` SDL bus (see "Submodule patches"). |
| [`scripts/web_port/gccollect.c.patch`](../scripts/web_port/gccollect.c.patch) | Conservative-GC fix for wasm applied to the unix port (see "Submodule patches"). |
| [`web/shell.html`](../web/shell.html) | The HTML shell template (`--shell-file`). Build copies the produced `micropython.html` to `index.html` and `mpos.html`. |
| `web/.preload_internal_filesystem/` | Auto-generated staging copy of `internal_filesystem/` (with web shims injected). Recreated on every build; do not edit by hand. |

The web-only Python shims (`_thread.py`, `socket.py`, `_webrepl.py`,
`websocket.py`, `task_handler.py`, `_web_machine_timer.py`) and the boot-time
`machine.Timer` injection are written into the staged filesystem by
`build_mpos.sh` (heredocs in the `web` target). They are **not** committed into
`internal_filesystem/` so device builds are unaffected.

---

## Submodule patches (applied automatically)

The web target requires four changes inside the `lvgl_micropython` submodule.
Rather than committing them to the submodule, they are stored in this repo and
applied at the start of the `web` build (`patch --forward` makes re-application a
no-op; the file copies are idempotent):

1. **`builder/web.py`** (full file) — the Emscripten build backend. Copied from
   `scripts/web_port/web.py`.
2. **`ext_mod/lcd_bus/sdl_bus/sdl_bus.h`** — adds a missing `uint32_t
   buffer_flags;` field to `mp_lcd_sdl_bus_obj_t` so its layout matches the
   generic `mp_lcd_bus_obj_t`. `lcd_panel_io_init()` casts the SDL object to the
   generic type and calls `panel_io_handle.init(...)`; without this field the
   offset of `panel_io_handle` differs on 32-bit/wasm and the indirect call
   reads the wrong function pointer → `function signature mismatch` trap. (On
   64-bit native, struct padding hid the bug.)
3. **`lib/micropython/ports/unix/gccollect.c`** — adds an `__EMSCRIPTEN__`
   branch to `gc_collect()` that uses `emscripten_scan_stack()` +
   `emscripten_scan_registers()` instead of the setjmp-based
   `gc_helper_collect_regs_and_stack()`. On wasm, live object pointers live in
   wasm locals/registers (not linear memory) and are invisible to a memory
   scan, so the stock collector freed in-use objects → `memory access out of
   bounds`. This matches the upstream MicroPython `ports/webassembly` approach
   and **requires ASYNCIFY** (so registers can be spilled), enabled via
   `-sASYNCIFY=1` in `web.py`.4. **`ext_mod/_webnet/`** (new files, not a patch) — the browser `fetch()`
   bridge for HTTP networking. `webnet.c` + `micropython.mk` are copied from
   `scripts/web_port/ext_mod/_webnet/`; the `.mk` only compiles it when
   `MPOS_WEB=1`. See *Networking* above.
### Updating a submodule patch

If you need to change one of the patched submodule files:

```bash
# Edit the file directly in the submodule, then regenerate the patch:
cd lvgl_micropython
git diff -- ext_mod/lcd_bus/sdl_bus/sdl_bus.h \
    > ../scripts/web_port/sdl_bus.h.patch

cd lib/micropython
git diff -- ports/unix/gccollect.c \
    > ../../../scripts/web_port/gccollect.c.patch

# For web.py, just copy it back:
cp lvgl_micropython/builder/web.py scripts/web_port/web.py
```

To verify reproducibility, revert the submodule files and rebuild — the build
should re-apply everything:

```bash
( cd lvgl_micropython \
    && git checkout -- ext_mod/lcd_bus/sdl_bus/sdl_bus.h \
    && rm -f builder/web.py ext_mod/lcd_bus/sdl_bus/sdl_bus.h.rej \
    && rm -rf ext_mod/_webnet )
( cd lvgl_micropython/lib/micropython && git checkout -- ports/unix/gccollect.c )
scripts/build_mpos_web.sh
```

The two C patches were verified to apply cleanly (`patch --forward`, exit 0, no
`.rej`) against the pinned commits listed in *Build from a fresh clone*.

---

## Build flags (in `scripts/web_port/web.py`)

The Emscripten link flags (`web_ldflags`) are the main tuning surface:

| Flag | Why |
| --- | --- |
| `-sUSE_SDL=2` | Use Emscripten's bundled SDL2 port. |
| `-sALLOW_MEMORY_GROWTH=1`, `-sINITIAL_MEMORY=...`, `-sMAXIMUM_MEMORY=...` | Heap sizing. |
| `-sSTACK_SIZE=8388608` | Larger stack for deep LVGL/MPOS call chains. |
| `-sASYNCIFY=1 -sASYNCIFY_STACK_SIZE=32768` | **Required** for `emscripten_scan_registers()` in the GC fix. |
| `-sFORCE_FILESYSTEM=1 -sEXIT_RUNTIME=0` | Keep the runtime + virtual FS alive. |
| `-Wl,--allow-multiple-definition` | MicroPython's libc `printf` vs Emscripten libc `printf` duplicate. |
| `-sASSERTIONS=2 --profiling-funcs` | **Debug only.** Symbolized stacks. Remove for an optimized production build. |

Module disabling and SDL include/link selection happen via `MPOS_WEB=1` and the
`MICROPY_PY_*=0` make variables, also set in `web.py`.

---

## Web-only Python shims (staged into `lib/`)

Written by `build_mpos.sh` into `web/.preload_internal_filesystem/lib/` so they
shadow frozen/native modules at runtime without affecting device builds:

| Shim | Replaces | Behavior |
| --- | --- | --- |
| `_thread.py` | native `_thread` | Cooperative: runs thread bodies as asyncio tasks; locks are no-ops; `get_ident()==1`. |
| `socket.py` | native `socket` | Stub; raises `OSError` on use (no browser raw sockets). |
| `_webrepl.py` / `websocket.py` | native modules | Stubs; raise `OSError` on use. |
| `task_handler.py` | frozen `task_handler` | Drives `lv.task_handler()` + `lv.tick_inc()` from an asyncio task instead of `machine.Timer`. Same public API (`TaskHandler`, `TASK_HANDLER_STARTED/FINISHED`, `add_event_cb`, `disable/enable`, `deinit`). |
| `_web_machine_timer.py` | `machine.Timer` | asyncio-backed periodic/one-shot timer. |

### `machine.Timer` injection

The native `machine` module dict is read-only, so `machine.Timer = ...` fails.
Instead, `build_mpos.sh` patches the **staged** copy of `main.py` (never the
device source) right after `sys.path.insert(0, "lib")` to replace
`sys.modules["machine"]` with a thin wrapper exposing `Timer` and delegating all
other attributes to the native module.

---

## Networking (HTTP via browser `fetch()`)

The browser has no raw TCP/UDP sockets, so `socket` is stubbed and
`MICROPY_PY_SOCKET=0`. HTTP instead goes through the browser's `fetch()` API via
a small native module plus an `aiohttp` shim:

| Piece | Location | Role |
| --- | --- | --- |
| `_webnet` native module | `scripts/web_port/ext_mod/_webnet/webnet.c` (+ `micropython.mk`) | C/`EM_JS` bridge to `fetch()`. Non-blocking, poll-based so the asyncio/UI loop keeps running. Built only for web (`MPOS_WEB=1`); copied into `lvgl_micropython/ext_mod/_webnet/` by `build_mpos.sh`. |
| `aiohttp` shim | staged `lib/aiohttp/__init__.py` (heredoc in `build_mpos.sh`) | Re-implements `ClientSession.get/post/put/...` on top of `_webnet`, polling with `await asyncio.sleep_ms(...)`. Re-exports the WebSocket names (`WSMsgType`, `WebSocketClient`, `ClientWebSocketResponse`) from the device `aiohttp_ws.py` so imports resolve. |

`_webnet` API: `fetch_start(method, url, headers_json, body)` returns an int
handle; then `poll(h)` (0 pending / 1 done / -1 error), `status(h)`,
`headers(h)`, `body(h)`, `error(h)`, and `free(h)`.

**Limitations:**

- **CORS applies.** Cross-origin requests fail unless the server sends
  `Access-Control-Allow-Origin`. The default app-store/OTA hosts do not, so those
  downloads fail in the browser with `fetch failed: TypeError: Failed to fetch` —
  this is a server-side policy, not a port bug. Same-origin or CORS-enabled
  endpoints work.
- **WebSockets not yet wired.** `ws_connect()` raises `NotImplementedError`; the
  WS symbols exist only so module imports (e.g. the Nostr service) succeed.

---

## Making changes — common scenarios

- **Change MPOS Python code / apps:** edit under `internal_filesystem/` as usual,
  then rebuild (`scripts/build_mpos_web.sh`). The staged FS is rebuilt every
  time, so changes are picked up. (The FS is baked into `micropython.data` at
  link time; a rebuild is required — there is no live file mount.)
- **Change the HTML/JS shell:** edit `web/shell.html`, rebuild. `index.html` and
  `mpos.html` are regenerated from it.
- **Change build/link flags:** edit `scripts/web_port/web.py`, rebuild.
- **Change a patched submodule C file:** see "Updating a submodule patch".
- **Add another web-only shim:** add a heredoc in the `web` branch of
  `scripts/build_mpos.sh` next to the existing shims.

---

## Testing in a browser

Serve with `scripts/run_web.sh` and open the page. When iterating, note that
`micropython.data` (the preloaded FS) is cached **separately** from the wasm, so
hard-reload / disable cache (or append a cache-busting query like `?v=2`) when
testing filesystem changes.

A clean boot prints the banner, the `RAM: ... free` line, then
`Passing execution over to mpos.main`, and renders the launcher. The following
console messages are **expected and non-fatal** in the browser:

- `no ADC` / `module 'machine' has no attribute 'ADC'` (no battery ADC)
- `mpos.imu.drivers.iio: Error listing dir` (no IMU)
- `download error` / `fetch failed: TypeError: Failed to fetch` for the default
  app-store/OTA hosts (CORS-blocked cross-origin requests — see *Networking*).
- `no module named 'esp32'`
- `aiorepl ... OSError: [Errno 29] EIO` (browser stdin cannot be read)

A **fatal** problem would instead show `memory access out of bounds`,
`function signature mismatch`, or `MicroPythonOS exiting`.

---

## Production build checklist

- Remove the debug flags `-sASSERTIONS=2 --profiling-funcs` from
  `web_ldflags` in `scripts/web_port/web.py`.
- Rebuild and serve the contents of `web/` from any static host.

---

## Deploying to GitHub Pages

[`scripts/deploy_web_pages.sh`](../scripts/deploy_web_pages.sh) builds the web
export and force-pushes the contents of `web/` as a single commit to a
`gh-pages` branch. It is a plain command (no GitHub Action / CI), so you run it
whenever you want to update the live site.

```bash
scripts/deploy_web_pages.sh                 # build, then deploy to remote `fork`
scripts/deploy_web_pages.sh --no-build      # deploy the existing web/ as-is
REMOTE=origin scripts/deploy_web_pages.sh   # deploy to a different remote
BRANCH=gh-pages scripts/deploy_web_pages.sh # use a different branch
```

One-time setup on GitHub: **Settings → Pages → Build and deployment → Source:
"Deploy from a branch", Branch: `gh-pages` / `(root)`**. The site is then served
at `https://<owner>.github.io/<repo>/`.

The script adds a `.nojekyll` file so Pages serves the underscore-prefixed
`.preload_internal_filesystem/` directory verbatim (Jekyll would otherwise skip
it). The `gh-pages` branch holds only generated artifacts and is overwritten on
every deploy.
