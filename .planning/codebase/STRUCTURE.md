# Codebase Structure

*Last updated: 2026-06-25*

## Repository Layout

```
.
├── AGENTS.md                       # Agent-specific guidance
├── CHANGELOG.md
├── Makefile                        # Make entry points
├── README.md
├── ruff.toml
├── internal_filesystem/            # One-to-one filesystem image; main source tree
│   ├── main.py                     # Boot shim; delegates to lib/mpos/main.py
│   ├── lib/                        # Libraries frozen or copied to device
│   │   ├── mpos/                   # MPOS framework
│   │   ├── drivers/                # Hardware drivers
│   │   ├── cryptography/           # Crypto helpers
│   │   ├── aiohttp/                # HTTP client
│   │   └── ...                     # MicroPython-lib ports (os, pathlib, queue, typing, etc.)
│   ├── apps/                       # User-installed / side-loaded apps
│   ├── builtin/apps/             # Pre-installed / built-in apps
│   ├── builtin/res/              # Shared resources (icons, emojis, boot logo)
│   ├── builtin/html/             # Inlined/minified WebREPL HTML
│   ├── data/                       # Runtime data on device
│   └── prefs/                      # SharedPreferences JSON stores
├── c_mpos/                         # C/C++ native modules
├── lvgl_micropython/               # lvgl_micropython submodule (MicroPython + LVGL)
├── micropython-camera-API/           # Camera driver submodule
├── micropython-nostr/                # Nostr submodule
├── secp256k1-embedded-ecdh/          # Crypto submodule
├── freezeFS/                         # Frozen filesystem submodule
├── esp32-component-rvswd/            # RVSWD component submodule
├── scripts/                          # Build, flash, install, controller scripts
├── tests/                            # Unit & graphical tests
├── manifests/                        # Frozen-module manifests
├── webrepl/                          # Source for inlined WebREPL UI
└── .planning/                        # Planning artifacts (this map)
```

## Framework module tree

- `internal_filesystem/lib/mpos/__init__.py` — primary public API facade.
- `internal_filesystem/lib/mpos/app/` — `App`, `Activity`, `Service`, common activities (`chooser.py`, `view.py`, `share.py`).
- `internal_filesystem/lib/mpos/ui/` — all UI utilities; notable files:
  - `appearance_manager.py` — themes/colors
  - `display_metrics.py` — resolution helpers
  - `font_manager.py` — scaled font / emoji rendering
  - `keyboard.py` — `MposKeyboard`
  - `testing.py` — UI automation helpers and test base classes
  - `topmenu.py` — status bar / drawer
  - `view.py` — screen stack and content view
- `internal_filesystem/lib/mpos/net/` — `connectivity_manager.py`, `download_manager.py`, `wifi_service.py`.
- `internal_filesystem/lib/mpos/content/` — `app_manager.py`, `intent.py`, `streaming_unzip.py`.
- `internal_filesystem/lib/mpos/audio/` — playback and recording codecs.
- `internal_filesystem/lib/mpos/board/` — board-specific initialization files (one per supported board).
- `internal_filesystem/lib/mpos/hardware/` — vendor-specific helpers (e.g. `fri3d/`).

## Apps Layout

Each app is a directory:

```
internal_filesystem/apps/<package.name>/
├── MANIFEST.JSON
├── icon_64x64.png
└── <entrypoint>.py                # Usually main.py
```

Older apps may keep icons under `res/mipmap-mdpi/`; the framework still supports that path but logs a deprecation warning.

Built-in apps live under `internal_filesystem/builtin/apps/<package.name>/` and are frozen into the firmware image via `freezeFS`.

## Naming Conventions

- Package names: Java/Android style reverse domains, e.g. `com.micropythonos.launcher`, `cz.ucw.pavel.weather`.
- Module names: lowercase with underscores (`activity_navigator.py`).
- Classes: PascalCase (`ActivityNavigator`, `DownloadManager`).
- App entrypoint classes: typically `MainActivity`.
- Manifest: `MANIFEST.JSON` (uppercase).

## Where Tests Live

- `tests/test_*.py` — unit tests.
- `tests/test_graphical_*.py` — LVGL/UI tests (runner treats these specially).
- `tests/manual_test_*.py` — not run automatically.
- `internal_filesystem/lib/mpos/testing/mocks.py` — centralized hardware/network mocks.
- `internal_filesystem/lib/mpos/ui/testing.py` — LVGL automation base classes.

## Key Files for Common Tasks

| Task | File |
|------|------|
| Add a board | `internal_filesystem/lib/mpos/main.py` → `detect_board()`; create `internal_filesystem/lib/mpos/board/<board>.py` |
| Add a built-in app | `internal_filesystem/builtin/apps/<pkg>/` + update freeze manifest |
| Add an installable app | `internal_filesystem/apps/<pkg>/` |
| Change boot flow | `internal_filesystem/lib/mpos/main.py` |
| Change framework API | `internal_filesystem/lib/mpos/__init__.py` |
| Build | `scripts/build_mpos.sh <target>` or `make build-mpos-unix` |
| Run tests | `make tests` |
| Deploy to device | `scripts/install.sh <pkg>` or mpremote via `scripts/mpos_controller.py` |
