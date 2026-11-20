# Official documentation review and targeted D-Shell checks, 2026-11-20

Historical intermediate 1.5.2 review. The current built-in 1.5.3 delivery and
its new device results are recorded in `appstore-builtin-2026-11-20.md`.
The default-provider and acceptance statements below describe that earlier
candidate only, not the current organization build.

The review covers the optional uPyStore integration in the official AppStore.
It reuses the November 19 installation, controlled helper-upgrade and manual
video evidence rather than presenting those tests as new runs of this version.

## Documentation and repository baseline

The current official AppStore files and AppManager were unchanged between the
previous review baseline and upstream main
`4e34dd67de5f90707926282d3da23d0862c462f2`. There were no corresponding upstream
changes to overwrite. The organization branch remains
`FreakStudioCN/MicroPythonOS:feature/appstore-upystore`, based on its existing
main `8484908a5ceade80a7a5854925b85d662a3b480b`.

Sources checked:

- Lifecycle: https://docs.micropythonos.com/apps/app-lifecycle/
- App structure / manifest: https://docs.micropythonos.com/apps/creating-apps/
- MPK layout: https://docs.micropythonos.com/apps/bundling-apps/
- Default backend / existing features: https://docs.micropythonos.com/apps/appstore/
- Storage: https://docs.micropythonos.com/architecture/filesystem/
- Imports and compiled entrypoints: https://docs.micropythonos.com/frameworks/app-manager/
- Async work: https://docs.micropythonos.com/frameworks/task-manager/
- Service lifecycle: https://docs.micropythonos.com/frameworks/service/
- Contributions: https://docs.micropythonos.com/other/merge-checklist/
- The repository's AGENTS.md, CONTRIBUTING.md and existing tests.

## Findings and changes

| Area | Finding / resulting behavior |
| --- | --- |
| Existing backend | Restored BadgeHub as the default; uPyStore is opt-in. Explicit saved choices are retained and invalid values fall back to BadgeHub. The D-Shell's earlier effective uPyStore choice was saved explicitly before restart. |
| App/module structure | The existing flat builtin app is compliant with the recommended layout. Kept the app identity, icon, Service and flat helper modules; no unnecessary assets tree or OS/library overlay. |
| Manifest | Migrated the deprecated category string to a categories list and increased the app version to 1.5.2. |
| Storage | Moved temporary downloads/staging to cache/com.micropythonos.appstore/install and receipts to prefs/com.micropythonos.appstore/receipts. Legacy receipts migrate on access; uninstall removes both copies so an old receipt cannot reappear. A pending old backup requires recovery before another install. |
| Activity lifecycle | Detail pause cancels its pending icon timer; per-callback tokens avoid LVGL wrapper identity assumptions and keep stale callbacks from consuming new timers. Destroyed pages release their own widgets. Store cleanup preserves a newer Activity's icon references. Late network completion cannot write to destroyed pages. |
| Entry compatibility | Kept same-filter main/launcher validation and safe paths. Added the .py-to-.mpy fallback and explicit .mpy entrypoints supported by AppManager; checks source syntax or compiled header/version without executing downloaded code during validation. Actual launch remains a separate check. |
| Integrity | Reject an unknown provider before it can fall through to a path without uPyStore integrity verification. Size, SHA256, strict archive paths and staged replacement remain. |
| Installation result | Failure to clean a temporary file after successful commit no longer reports that committed installation as failed. Cleanup problems remain logged. |
| Updates | Foreground and Service share the provider preference; background checks ignore foreground search and include revisions. Kept Update All, notification navigation and original BadgeHub rating/report behavior. |
| Diagnostics | Replaced new unconditional print diagnostics with project logging and guarded debug messages. |
| Contribution | Updated CHANGELOG, manifest, reproduction instructions and regression tests. No new board or framework is introduced, so MAINTAINERS is unchanged. PR submission and upstream merge are separate states; this branch does not claim an upstream merge. |

The change retains official list/detail UI, icons and placeholders, categories,
Installed/Updates, versions, Open/Uninstall/Update, Update All, boot checks and
notifications, Settings, BadgeHub selection and the existing QR entry. A retained
camera/QR path is not new D-Shell camera acceptance. uPyStore rating submission
has no supplied contract; optional profile/install telemetry is outside this scope.

## Verification

Failing regressions were recorded before the corresponding fixes. After fixes:

- 40 CPython tests passed: 27 existing integration tests plus 13 review cases.
- 116 native MicroPython tests passed: update flow 62, async refresh 23,
  uninstall refresh 3, list build 3, ratings 15, install safety/lifecycle 10.
- `make lint`, `make syntax-tests` and `git diff --check` passed.
- The MPK layout and temporary install validation passed.
- The static API checker has 41 inherited findings plus one return-type inference
  finding for `lv.timer_create.delete`. The official API reference contains
  `lv.timer_t.delete`, and the actual ESP32 `lv_timer_t` cancellation and stale
  callback check passed. The raw checker is not reported as a clean pass.
- The native headless runner is a unit-test environment, not a full desktop OS
  preview. The earlier precompiled SDL startup limitation is unchanged.

Targeted device: D-Shell ESP32-S3 N16R8, 240 x 320 ST7789V / GT911, 80 MHz SPI,
existing MicroPythonOS 0.21.2 / API 0. No firmware or global library was replaced.

| Targeted check on 1.5.2 | Result |
| --- | --- |
| Installed source identity | All nine installed files match the new MPK; version and selected source match. |
| Legacy receipt | The calculator's fullname, source, version, revision, slug and hash are unchanged after migration to prefs. |
| Actual LVGL timer | Pause cancels lv_timer_t; a stale callback is harmless; destroyed detail widgets are released. |
| Compiled entry | A controlled local package declaring main.py and containing only main.mpy passed install validation and executed CompiledProbe with its expected marker. This is not a published uPyStore package. |
| Uninstall | Official Uninstall removed the user app and both canonical/legacy receipt locations. |
| Real reinstall | Real HTTPS metadata and MPK requests for CC Skill Smoke 1.0.0/r1 succeeded using the new cache/prefs layout; stage/backup emptied. |
| Actual application | Official Open launched CalculatorActivity; its actual button matrix produced 2 + 3 = 5. |
| Cleanup | Returning through the real Activities released their widgets. The compiled fixture was uninstalled, test transport aliases restored, network/event loop remained alive and the device returned to Launcher. |

AppStore 1.5.2 local revision 2 MPK: 33765 bytes, SHA256
`44d12f0aca137169e71ebc9caeca1e7141eef1a8b72b344549d201925c5a3ff1`.
It is an unpublished development artifact. The calculator package remains
3872 bytes, SHA256
`44b63bb4af00613edea5ce01069aa58e3032a7dad81a7e350b263c35a75418b6`.

## Evidence reuse and unresolved items

The November 19 report remains the baseline for full catalog browsing,
categories, manual touch and operation video, physical network interruption,
negative packages, and controlled two-application helper upgrades. The targeted
checks above are new November 20 observations; the old video is not relabeled
as filming 1.5.2. Neither controlled upgrades nor a calculator test establishes
compatibility of every catalog app.

Still open:

- A trusted helper-containing app with two published revisions is needed for a
  real online upgrade case; the publisher must provide it.
- Background TLS/timeouts remain. The November 20 device log again recorded
  TimeoutError at https://upystore.io/api/v1/apps?limit=100&page=3&q= while the
  foreground calculator chain recovered and passed. Prior page 6 TLS -29312,
  icon/header errors and the independent OSUpdate failure remain evidence for
  OS/transport and store maintainers; no blanket server-side diagnosis is made.
- Danke and Show Battery require publisher-side package repairs unless new
  packages are published. Their path checks remain strict.
- The obsolete sample and calculator single-file 404s remain tracked separately
  from the working whole-package path. OTA is not accepted from an empty
  firmware-release list.

Published-revision upgrade, repeated network stability, all-app compatibility,
camera/QR and OTA remain outside the accepted result.

Upstream PR submission is on hold at the user's request. No official PR has
been opened for this work. In issue #207, ThomasFarstrike proposed a separate
AppStore frontend for each backend, and leezisheng agreed. The current built-in
multi-backend integration therefore needs an architectural discussion before
submission; successful tests do not establish upstream acceptance.

- Discussion: https://github.com/MicroPythonOS/MicroPythonOS/issues/207
- Proposal: https://github.com/MicroPythonOS/MicroPythonOS/issues/207#issuecomment-5159309894
- Agreement: https://github.com/MicroPythonOS/MicroPythonOS/issues/207#issuecomment-5159330703
