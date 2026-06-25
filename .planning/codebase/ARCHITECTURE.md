# Architecture

*Last updated: 2026-06-25*

## High-Level Pattern

MicroPythonOS follows an Android-inspired app model:

- **Apps** are packages with a `MANIFEST.JSON` and an entrypoint module.
- **Activities** are UI screens with lifecycle callbacks (`onCreate`, `onStart`, `onResume`, `onPause`, `onStop`, `onDestroy`, `onBackPressed`).
- **Intents** describe an action to perform or a target activity; the system resolves handlers via `AppManager`.
- **Services** run background work (e.g. `boot_completed` actions).

## Boot & Entry Points

1. `internal_filesystem/main.py` (frozen or on-disk) inserts `lib/` into `sys.path`, ensures `os.path` is available, and imports `mpos.main`.
2. `internal_filesystem/lib/mpos/main.py`:
   - Initializes LVGL.
   - Detects the board (`detect_board()`), then imports the matching `mpos.board.<board>` module.
   - Sets up display metrics, boot splash, notification bar, drawer, swipe gestures, focus group.
   - Starts the launcher app and optional `auto_start_app`/`auto_start_app_early`.
   - Starts boot-completed services.
   - Enters the `TaskManager` asyncio loop (does not return).

## Core Framework Layers

| Layer | Key files |
|-------|-----------|
| Application model | `internal_filesystem/lib/mpos/app/app.py`, `app/activity.py`, `app/service.py` |
| Navigation / lifecycle | `internal_filesystem/lib/mpos/activity_navigator.py`, `ui/view.py` |
| App registry & install | `internal_filesystem/lib/mpos/content/app_manager.py`, `content/intent.py`, `content/streaming_unzip.py` |
| Async runtime | `internal_filesystem/lib/mpos/task_manager.py` |
| UI shell | `internal_filesystem/lib/mpos/ui/topmenu.py`, `ui/view.py`, `ui/appearance_manager.py`, `ui/input_manager.py` |
| Shared prefs / data | `internal_filesystem/lib/mpos/shared_preferences.py` |
| Hardware abstraction | `internal_filesystem/lib/mpos/board/*.py`, `lib/drivers/` |

## Activity Lifecycle & Screen Stack

- `ui.view.screen_stack` holds tuples of `(activity, screen, focusgroup, focused_obj)`.
- `setContentView()` pushes a new screen, calls lifecycle methods, and plays a screen transition.
- `back_screen()` first closes the drawer, then calls `onBackPressed()` if overridden, otherwise finishes the activity.
- `finish_current_activity()` pops to the previous screen and calls `onResume()`.
- Lifecycle exceptions are caught and shown with `mpos.ui.errordialog.show_app_error_dialog()`.

## Intent Resolution

- Explicit intents: provide an `Activity` subclass directly.
- Implicit intents: an `action` string (e.g. `main`, `boot_completed`, `VIEW`, `OPEN`) is resolved by `AppManager.resolve_activity()`.
- Manifest-declared file handlers include `mimeType` and/or `pathPattern`; matching handlers are lazily imported from the app package.
- `ChooserActivity` is shown when multiple handlers match.

## Concurrency Model

- **Single asyncio loop** driven by `TaskManager` (10 ms tick). Most cooperative code uses `TaskManager.create_task()`.
- **`_thread`** is available but discouraged; `TaskManager.start_new_thread()` warns callers about limited, non-preemptive threads.
- UI must be updated from the main thread or via `lv.async_call()`; `Activity.update_ui_threadsafe_if_foreground()` wraps this.

## Data Flow Examples

- Boot: `main.py` → `mpos.main` → board init → launcher → services.
- Open With: App builds an `Intent` with action/path → `ActivityNavigator` → `AppManager._import_handler_class()` → target activity runs in app context.
- App install: `AppManager.download_and_install_package()` → streaming HTTP → streaming ZIP → `refresh_apps()`.

## Key Abstractions

- `mpos.App`, `mpos.Activity`, `mpos.Service`, `mpos.Intent` — public app model.
- `DisplayMetrics` — resolution/DPI helpers; apps should use this instead of hardcoding pixels.
- `MposKeyboard` — on-screen keyboard wrapper over LVGL keyboard widget.
- `SettingsActivity` / `SettingActivity` — framework helpers for preference screens.
- `NotificationManager` + top bar for system notifications.
