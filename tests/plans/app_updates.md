# App Store "Updates Available" Flow — Test Coverage Analysis

## Summary

**The update-checking pipeline has almost no direct test coverage.** The existing tests touch only two peripheral edges: (1) that `_run_update_all` calls `refresh_apps` + `check_for_updates_now` after completion, and (2) that the "Update N App(s)" button is focus-reachable via arrow keys. Every other aspect — the boot service, the state machine, the network interactions, the notification posting, the notification click→launch path, the sequential per-app update flow, what happens after updates complete — has zero tests.

---

## Coverage Table

| # | Aspect | Test file(s) | Status |
|---|--------|-------------|--------|
| 1 | `boot_completed` event → `AppStoreService.onStart()` starts `AppUpdateManager` | *none* | **GAP** |
| 2 | `AppUpdateManager.start()` — sets `_running`, registers connectivity callback, launches `_run_loop()` | *none* | **GAP** |
| 3 | 120s `BOOT_INITIAL_DELAY` before first update check | *none* | **GAP** |
| 4 | Connectivity guard — `is_online()` must return True before `check_for_updates()` runs | *none* | **GAP** |
| 5 | Offline behavior — logs "offline, skipping check" and re-sleeps 24h | *none* | **GAP** |
| 6 | `_network_changed(offline)` → transitions to `WAITING_WIFI` when checking | *none* | **GAP** |
| 7 | `_network_changed(online)` → re-triggers check from `WAITING_WIFI`/`ERROR` states | *none* | **GAP** |
| 8 | `check_for_updates()` — downloads app index JSON from configured backend | *none* | **GAP** |
| 9 | `check_for_updates()` — handles download network error (→ `WAITING_WIFI` or `ERROR`) | *none* | **GAP** |
| 10 | `check_for_updates()` — handles JSON parse error (→ `ERROR`) | *none* | **GAP** |
| 11 | `check_for_updates()` — version comparison against installed apps (BadgeHub format: `slug`/`version`) | *none* | **GAP** |
| 12 | `check_for_updates()` — version comparison against installed apps (GitHub format: `fullname`/`version`) | *none* | **GAP** |
| 13 | `check_for_updates()` — state transitions: IDLE→CHECKING→UPDATES_AVAILABLE | *none* | **GAP** |
| 14 | `check_for_updates()` — state transitions: IDLE→CHECKING→NO_UPDATES | *none* | **GAP** |
| 15 | `check_for_updates()` — `_check_in_progress` guard prevents overlapping checks | *none* | **GAP** |
| 16 | `check_for_updates_now()` — skips if `_check_in_progress` is True | *none* | **GAP** |
| 17 | 24-hour re-check cycle (the `_run_loop` sleep loop) | *none* | **GAP** |
| 18 | `_notify_updates_available()` — builds Notification with correct ID, title, text, intent, auto_cancel | *none* | **GAP** |
| 19 | `_notify_updates_available()` — `suppress_notifications=True` skips posting | *none* | **GAP** |
| 20 | `_clear_notification()` — calls `NotificationManager.cancel("appstore.updates_available")` | *none* | **GAP** |
| 21 | Notification click → `NotificationManager.trigger()` → `_dispatch_intent()` → launches `com.micropythonos.appstore` | *none* | **GAP** |
| 22 | `onResume()` — attaches state callback, sets `suppress_notifications=True`, calls `_sync_update_banner()` with current state | *none* | **GAP** |
| 23 | `onPause()` — detaches state callback, sets `suppress_notifications=False` | *none* | **GAP** |
| 24 | `_on_update_state_change()` — calls `_sync_update_banner()` only when app has foreground | *none* | **GAP** |
| 25 | `_sync_update_banner(UPDATES_AVAILABLE)` — shows button, sets "Update N App(s)" label, pushes list down | *none* (partial in focus test) | **GAP** |
| 26 | `_sync_update_banner(any_other_state)` — hides button, moves list back up | *none* | **GAP** |
| 27 | `_sync_update_banner()` — shows/hides per-app "Update available" labels based on updatable set | *none* | **GAP** |
| 28 | "Update N App(s)" button — focusable and reachable via DOWN from settings button | `test_graphical_appstore_focus.py` | ✅ Covered |
| 29 | `_update_all_click()` — retrieves `updatable_apps` and calls `_run_update_all()` | *none* | **GAP** |
| 30 | `_run_update_all()` — disables button at start | *none* | **GAP** |
| 31 | `_run_update_all()` — sequentially downloads and installs each app, updating label text | *none* | **GAP** |
| 32 | `_run_update_all()` — fetches BadgeHub details for apps missing `download_url` | *none* | **GAP** |
| 33 | `_run_update_all()` — handles per-app install failures, shows error in label, continues to next app | *none* | **GAP** |
| 34 | `_run_update_all()` — handles out-of-space error ("Not enough free space") | *none* | **GAP** |
| 35 | `_run_update_all()` — calls `AppManager.refresh_apps()` after all updates complete | `test_appstore_async_refresh.py` (`TestAppStoreUpdateAllRecheck`) | ✅ Covered |
| 36 | `_run_update_all()` — calls `AppUpdateManager.check_for_updates_now()` after refresh | `test_appstore_async_refresh.py` (`TestAppStoreUpdateAllRecheck`) | ✅ Covered |
| 37 | `_run_update_all()` — re-enables button, clears apps, calls `refresh_list()` after completion | *none* | **GAP** |
| 38 | Post-update: button hidden when re-check finds no updates | *none* | **GAP** |
| 39 | Post-update: list moves back up and scrolls normally | *none* | **GAP** |
| 40 | `AppDetail._trigger_update_recheck()` — calls `refresh_apps` + schedules `check_for_updates` | `test_appstore_async_refresh.py` (`TestAppDetailUpdateRecheck`) | ✅ Covered |

---

## Summary Statistics

- **Total aspects identified:** 40
- **Covered:** 4 (10%)
- **Gaps:** 36 (90%)

## Serious Gaps (High Priority)

These are the aspects most likely to regress silently:

1. **Boot service wiring** — If the MANIFEST.JSON or service class changes, nothing catches that the update checker never starts at boot.
2. **`check_for_updates()` state machine and network error handling** — The entire core logic of fetching the index, parsing JSON, comparing versions, and transitioning states is untested. Every network error path (download fails, JSON corrupt, offline mid-check) and both backend formats (BadgeHub vs GitHub) have zero coverage.
3. **Notification posting and click→launch** — The "App updates available" notification is the only user-visible signal outside the AppStore UI. If the notification ID, intent, or auto_cancel flag change, no test fails.
4. **`_run_update_all()` sequential per-app update** — Only the *post* loop (`refresh_apps` + `check_for_updates_now`) is tested. The actual per-app download+install, progress updates, error handling, and out-of-space handling are not.
5. **Post-update UI cleanup** — After all updates complete and the re-check finds zero updates, there is no test that verifies the button is hidden, the list repositions, and normal scrolling works.
6. **`suppress_notifications`** — The toggle in `onResume`/`onPause` is untested; a bug here silently suppresses all future notifications.
