# Technology Stack

*Last updated: 2026-06-25*

## Overview

MicroPythonOS is a graphical operating system for microcontrollers. The runtime is built on `lvgl_micropython`, a fork of MicroPython that bundles LVGL 9.x. Application code is almost entirely MicroPython; a small number of C modules provide performance-sensitive peripherals and third-party libraries.

## Languages

| Language | Use |
|----------|-----|
| MicroPython / Python 3 | Application framework, built-in apps, app store apps, tests |
| C / C++ | Native modules, display/touch drivers, audio codecs, QR decode, Doom port |
| Bash | Build scripts, flashing, release tooling |
| CMake | Native module build descriptors |

## Runtime

- **MicroPython** — `lvgl_micropython/lib/micropython` submodule, based on MicroPython 1.25.0 era.
- **LVGL 9.x** — `lvgl_micropython/lib/lvgl` submodule; graphics library and widget toolkit.
- **asyncio** — used only via `TaskManager`; apps are not expected to import `asyncio` directly.
- **Viper / native decorators** — enabled on ESP32; disabled by `scripts/build_mpos.sh` for `unix`/`macOS` frozen builds because they cause Mach-O/link errors.

## Build & Development Tooling

- `Makefile` — preferred entry points: `make build-mpos-unix`, `make tests`, `make lint`, `make syntax-tests`, `make unittest-tests`.
- `scripts/build_mpos.sh <target>` — main build driver for `unix`, `macOS`, `esp32`, `esp32s3`, `esp32-small`, `lilygo_t4`, `unphone`.
- `pytest` / `ruff` — Python linting (`uv tool run ruff check .`).
- `mpy-cross` — syntax validation; binary at `lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross`.
- `mpremote` — device deployment, packaged under `lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py`.
- `freezeFS` — submodule used to freeze the `builtin/` file tree into the firmware image.
- `mklittlefs` / custom scripts — firmware image and filesystem packing.

## Key Configuration Files

- `manifests/manifest.py` — frozen-module manifest (`freeze('../internal_filesystem/', ...)`).
- `ruff.toml` — linting config; excludes submodules and the `tests/` directory for now.
- `.gitmodules` — submodules: `freezeFS`, `secp256k1-embedded-ecdh`, `lvgl_micropython`, `micropython-camera-API`, `micropython-nostr`, `esp32-component-rvswd`.
- Board-specific configuration lives in `internal_filesystem/lib/mpos/board/*.py`.

## Native / C Modules (`c_mpos/`)

| Module | File | Purpose |
|--------|------|---------|
| `breakout` | `c_mpos/breakout/breakout.c` | Breakout game render helpers |
| `doomgeneric` | `c_mpos/doomgeneric/` | Chocolate Doom port for MPOS |
| `adc_mic` | `c_mpos/src/adc_mic.c` | Analog microphone support |
| `pdm_mic` | `c_mpos/src/pdm_mic.c` | PDM microphone support |
| `quirc_decode` | `c_mpos/src/quirc_decode.c` | QR code decoding (wraps `quirc`) |
| `rvswd` | `c_mpos/src/rvswd_module.c` | ESP32 component for RVSWD |
| `webcam` | `c_mpos/src/webcam.c` | Camera / webcam integration |

`c_mpos/micropython.cmake` declares the MicroPython bindings for `c_mpos`.

## Embedded Cryptography

- `secp256k1-embedded-ecdh` submodule — secp256k1 ECDH for Nostr / crypto flows.
- `micropython-nostr` submodule — Nostr protocol implementation.
- `internal_filesystem/lib/secp256k1.py` / `secp256k1_compat.py` — pure-Python wrappers.

## Display / Input Stack

- SDL on desktop (`DISPLAY=sdl_display`, `INDEV=sdl_pointer`).
- Board-specific display drivers in `internal_filesystem/lib/drivers/display/` and `lib/mpos/board/*.py`.
- Touch handled through LVGL indev drivers (SDL pointer on desktop, hardware controllers on device).
