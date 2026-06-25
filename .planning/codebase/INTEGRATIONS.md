# External Integrations

*Last updated: 2026-06-25*

## Overview

MicroPythonOS is mostly offline-first, but it integrates with external services for app distribution, time sync, weather, Nostr, and device management. Network access is gated through `mpos.net` modules.

## App Store & OTA

- The built-in app store fetches app manifests and `.mpk` packages from a remote repository / API.
- Downloads are streamed via `mpos.net.download_manager.DownloadManager` directly into `mpos.content.streaming_unzip.StreamingUnzip`.
- OTA firmware updates are handled by `esp32.Partition` rollback/cancel logic in `internal_filesystem/lib/mpos/main.py`.
- Known endpoint: BadgeHub `/report/install` (currently not used; commented in `internal_filesystem/builtin/apps/com.micropythonos.appstore/assets/app_detail.py`).

## Network Stack

- **WiFi** — `internal_filesystem/lib/mpos/net/wifi_service.py`; also managed by `internal_filesystem/lib/mpos/net/connectivity_manager.py`.
- **HTTP client** — aiohttp-like `aiohttp` module at `internal_filesystem/lib/aiohttp/` and the download manager.
- **WebSocket** — `internal_filesystem/lib/uaiowebsocket.py`.
- **WebREPL / WebServer** — `internal_filesystem/lib/mpos/webserver/`: `webserver.py`, `webrepl.py`, `webrepl_http.py`.

## Nostr

- `internal_filesystem/apps/com.micropythonos.nostr/` — Nostr client app.
- `micropython-nostr` submodule — protocol library.
- `secp256k1-embedded-ecdh` submodule — key exchange primitives.

## Time & Location

- **NTP / timezone** — `internal_filesystem/lib/mpos/time_zone.py`, `time_zones.py`, and `lib/localPTZtime.py` for local-time calculations.
- **GPS** — `internal_filesystem/lib/mpos/gps_manager.py`.

## Hardware Peripherals

Integration points with the physical world:

| Peripheral | Module |
|------------|--------|
| Camera (OV3660 / esp32-camera) | `internal_filesystem/lib/mpos/camera_manager.py`, `micropython-camera-API` submodule |
| IMU | `internal_filesystem/lib/mpos/imu/` + drivers |
| Audio (I2S, ADC, PDM, RTTTL, WAV) | `internal_filesystem/lib/mpos/audio/` |
| LoRa | `internal_filesystem/lib/mpos/lora_manager.py` |
| IR TX/RX | `internal_filesystem/lib/mpos/ir_manager.py` |
| Battery / power | `internal_filesystem/lib/mpos/battery_manager.py` |
| Haptic | board-specific files, e.g. `internal_filesystem/lib/mpos/board/fri3d_2024.py` |
| SD card | `internal_filesystem/lib/mpos/sdcard.py` |
| LED strips | `internal_filesystem/lib/mpos/lights.py` |

## USB / CDC / UART

- USB device support is frozen from `lvgl_micropython/lib/micropython/lib/micropython-lib/micropython/usb/` via `manifests/manifest.py`.
- ESP32 builds can enable a UART-based REPL at runtime (`esp.uart_repl(False/True)`), patched by `scripts/build_mpos.sh`.

## Build-Time Third-Party Sources

- `lvgl_micropython/lib/SDL` — SDL for desktop builds.
- `lvgl_micropython/lib/lvgl` — LVGL.
- `lvgl_micropython/lib/micropython` — MicroPython runtime.
- `lvgl_micropython/lib_lvgl_src_font/` — customized LVGL font sources copied into the LVGL tree during build.

## External API Call Patterns

- `DownloadManager.download_url(url, chunk_callback=..., total_size=...)` — primary HTTP download primitive.
- `ConnectivityManager` orchestrates WiFi connection state and exposes status to the UI.
- `WebServer` provides a local HTTP/WebREPL interface for host-side control (`scripts/mpos_controller.py`).
