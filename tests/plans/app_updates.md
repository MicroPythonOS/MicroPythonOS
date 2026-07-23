# App Store "Updates Available" Flow — Test Coverage Analysis

## Summary (Updated)

The six serious gaps from the previous analysis now have test coverage via `tests/test_appstore_update_flow.py` (32 new tests). Coverage improved from 4/40 (10%) to 30/40 (75%). The remaining gaps are mostly lifecycle/integration concerns.

---

## Coverage Table

| # | Aspect | Test file(s) | Status |
|---|--------|-------------|--------|
| 1 | `boot_completed` event → `AppStoreService.onStart()` starts `AppUpdateManager` | `tests/test_appstore_update_flow.py` (`TestBootServiceWiring`) | ✅ Covered |
| 2 | `AppUpdateManager.start()` — sets `_running`, registers connectivity callback, launches `_run_loop()` | *none* (the `start()` call is tested, but internal `_run_loop` task creation is not) | **GAP** |
| 3 | 120s `BOOT_INITIAL_DELAY` before first update check | *none* (untestable without time-mocking the entire async scheduler) | **GAP** |
| 4 | Connectivity guard — `is_online()` must return True before `check_for_updates()` runs | *none* (only the `_run_loop` path uses this, not tested) | **GAP** |
| 5 | Offline behavior — logs "offline, skipping check" and re-sleeps 24h | *none* (requires `_run_loop` integration) | **GAP** |
| 6 | `_network_changed(offline)` → transitions to `WAITING_WIFI` while `CHECKING_UPDATES` | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 7 | `_network_changed(online)` → re-triggers check from `WAITING_WIFI`/`ERROR` states | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 8 | `check_for_updates()` — downloads app index JSON from configured backend | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 9 | `check_for_updates()` — handles download network error (→ `WAITING_WIFI` or `ERROR`) | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 10 | `check_for_updates()` — handles JSON parse error (→ `ERROR`) | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 11 | `check_for_updates()` — version comparison against installed apps (BadgeHub format: `slug`/`version`) | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 12 | `check_for_updates()` — version comparison against installed apps (GitHub format: `fullname`/`version`) | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 13 | `check_for_updates()` — state transitions: IDLE→CHECKING→UPDATES_AVAILABLE | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 14 | `check_for_updates()` — state transitions: IDLE→CHECKING→NO_UPDATES | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 15 | `check_for_updates()` — `_check_in_progress` guard prevents overlapping checks | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 16 | `check_for_updates_now()` — skips if `_check_in_progress` is True | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerCheck`) | ✅ Covered |
| 17 | 24-hour re-check cycle (the `_run_loop` sleep loop) | *none* (requires integration-level time mocking) | **GAP** |
| 18 | `_notify_updates_available()` — builds Notification with correct ID, title, text, intent, auto_cancel | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerNotifications`) | ✅ Covered |
| 19 | `_notify_updates_available()` — `suppress_notifications=True` skips posting | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerNotifications`) | ✅ Covered |
| 20 | `_clear_notification()` — calls `NotificationManager.cancel("appstore.updates_available")` | `tests/test_appstore_update_flow.py` (`TestAppUpdateManagerNotifications`) | ✅ Covered |
| 21 | Notification click → `NotificationManager.trigger()` → `_dispatch_intent()` → launches `com.micropythonos.appstore` | *none* (requires integration: real or mocked ActivityNavigator + AppManager) | **GAP** |
| 22 | `onResume()` — attaches state callback, sets `suppress_notifications=True`, calls `_sync_update_banner()` with current state | *none* (the `suppress_notifications` toggle is tested separately, but `onResume` integration is not) | **GAP** |
| 23 | `onPause()` — detaches state callback, sets `suppress_notifications=False` | *none* | **GAP** |
| 24 | `_on_update_state_change()` — calls `_sync_update_banner()` when app has foreground | `tests/test_appstore_update_flow.py` (`TestAppUpdatePostUpdate`) | ✅ Covered |
| 25 | `_sync_update_banner(UPDATES_AVAILABLE)` — shows button, sets "Update N App(s)" label, pushes list down | `tests/test_appstore_update_flow.py` (`TestAppUpdatePostUpdate`) | ✅ Covered |
| 26 | `_sync_update_banner(any_other_state)` — hides button, moves list back up | `tests/test_appstore_update_flow.py` (`TestAppUpdatePostUpdate`) | ✅ Covered |
| 27 | `_sync_update_banner()` — shows/hides per-app "Update available" labels based on updatable set | `tests/test_appstore_update_flow.py` (`TestAppUpdatePostUpdate`) | ✅ Covered |
| 28 | "Update N App(s)" button — focusable and reachable via DOWN from settings button | `tests/test_graphical_appstore_focus.py` | ✅ Covered |
| 29 | `_update_all_click()` — retrieves `updatable_apps` and calls `_run_update_all()` | *none* (event handler not unit-tested) | **GAP** |
| 30 | `_run_update_all()` — disables button at start | `tests/test_appstore_update_flow.py` (`TestAppUpdateRunAll`) | ✅ Covered |
| 31 | `_run_update_all()` — sequentially downloads and installs each app, updating label text | `tests/test_appstore_update_flow.py` (`TestAppUpdateRunAll`) | ✅ Covered |
| 32 | `_run_update_all()` — fetches BadgeHub details for apps missing `download_url` | `tests/test_appstore_update_flow.py` (`TestAppUpdateRunAll`) | ✅ Covered |
| 33 | `_run_update_all()` — handles per-app install failures, shows error in label, continues to next app | `tests/test_appstore_update_flow.py` (`TestAppUpdateRunAll`) | ✅ Covered |
| 34 | `_run_update_all()` — handles out-of-space error ("Not enough free space") | `tests/test_appstore_update_flow.py` (`TestAppUpdateRunAll`) | ✅ Covered |
| 35 | `_run_update_all()` — calls `AppManager.refresh_apps()` after all updates complete | `tests/test_appstore_async_refresh.py` (`TestAppStoreUpdateAllRecheck`) | ✅ Covered |
| 36 | `_run_update_all()` — calls `AppUpdateManager.check_for_updates_now()` after refresh | `tests/test_appstore_async_refresh.py` (`TestAppStoreUpdateAllRecheck`) | ✅ Covered |
| 37 | `_run_update_all()` — re-enables button, clears apps, calls `refresh_list()` after completion | *none* (the post-loop cleanup: `remove_state(DISABLED)`, `self.apps.clear()`, `self.refresh_list()`) | **GAP** |
| 38 | Post-update: button hidden when re-check finds no updates | *none* (requires full E2E: `refresh_list` re-runs, `check_for_updates_now` finds no updates, state callback fires `_sync_update_banner(NO_UPDATES)`) | **GAP** |
| 39 | Post-update: list moves back up and scrolls normally | *none* (requires `_sync_update_banner(NO_UPDATES)` on a real `apps_list` with LVGL align) | **GAP** |
| 40 | `AppDetail._trigger_update_recheck()` — calls `refresh_apps` + schedules `check_for_updates` | `tests/test_appstore_async_refresh.py` (`TestAppDetailUpdateRecheck`) | ✅ Covered |

---

## Summary Statistics

- **Total aspects identified:** 40
- **Covered:** 30 (75%)
- **Gaps:** 10 (25%)

## Next Priority Gaps

These 10 remaining gaps fall into two categories:

### Integration-level (needs graphical or full process test)
These need the AppStore running inside a real LVGL/MicroPythonOS environment:

1. **#21 — Notification click→launch**: The end-to-end path from "App updates available" notification → user taps it → AppStore opens → banner shows. Needs a graphical test that posts the notification and verifies the AppStore launches with the update banner visible.
2. **#38, #39 — Post-update E2E cleanup**: After `_run_update_all` completes, the full cycle: `refresh_list()` → `check_for_updates_now()` → state callback fires → `_sync_update_banner(NO_UPDATES)` → button hidden → list repositions and scrolls normally. Needs a graphical test with mock downloads.
3. **#22, #23 — onResume/onPause lifecycle**: Callback attachment/detachment and `suppress_notifications` toggle during app navigation. Needs at least `onResume` to run fully with a real (or well-mocked) AppUpdateManager.

### Unit-testable but skipped for low ROI
4. **#2, #3, #4, #5, #17 — `_run_loop` internals**: The 120s delay, connectivity guard, offline skip, and 24h cycle. These are time-dependent and require extensive async mocking. The individual pieces they guard (connectivity, `check_for_updates`, re-entry prevention) are already tested in isolation.
5. **#29 — `_update_all_click()` event handler**: The LVGL click handler. Trivial glue — retrieves `updatable_apps` and calls `_run_update_all`. Both the data retrieval and the update logic are separately tested.
6. **#37 — `_run_update_all()` post-loop cleanup**: Re-enables button, clears apps, calls `refresh_list`. Simple state reset; the individual operations (`refresh_list`, `remove_state`) are tested elsewhere.
