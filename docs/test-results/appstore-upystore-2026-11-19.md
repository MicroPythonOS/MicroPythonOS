# Official AppStore / D-Shell acceptance, 2026-11-19

This records the official AppStore integration, not the earlier standalone
`com.freakstudio.upystore` prototype. Results cover the named device, packages
and cases. They do not establish compatibility of every catalog application.

## Versions and reproducible artifacts

| Item | Value |
| --- | --- |
| Repository / branch | FreakStudioCN/MicroPythonOS / feature/appstore-upystore |
| Source base | 8484908a5ceade80a7a5854925b85d662a3b480b |
| Device | D-Shell, ESP32-S3 N16R8, 16 MiB Flash / 8 MiB PSRAM |
| Display / input | ST7789V, 240 x 320, 80 MHz SPI / GT911 |
| Existing firmware | MicroPythonOS 0.21.2, API 0; no firmware reflash for this change |
| Running image length / SHA256 | 3559200 bytes / c72e27e795441c4ab2077e97cced514ea7ac825be0e29851a5ca790ea49fd0a9 |
| AppStore | com.micropythonos.appstore 1.5.1, local unpublished revision 1 |
| MPK | com.micropythonos.appstore_r1.mpk, 32845 bytes |
| MPK SHA256 | 8e0637b2d07524368a0f976ec0da0a58ea7128fc495f7016472bc60c63879ce7 |

Build the MPK with `python scripts/package_appstore.py --revision 1`. Its
deterministic contents and nine installed file hashes are recorded in
`release.json`. The MPK was transferred, verified, installed as a complete `/apps`
override, and the device restarted with `machine.reset()`. Filesystem hashes and
the loaded helper module paths were checked. This restart is not a physical
unplug/replug cold-start claim. No `/lib/mpos` overlay was deployed.

## Retained official functionality

The official app identity, list/detail screens, icons and placeholders, category
dropdown, Installed/Updates, version display, Open/Uninstall/Update, Update All,
boot update service and notification navigation remain. Existing icon, WIP and
notification settings and the QR entry remain. Store Source and Search Store use
the original settings screens. BadgeHub remains selectable; its existing
reporting/rating path is retained in code and regression coverage, not accepted
as a newly completed live BadgeHub service test.

Frontend and background checks share the provider preference. Background checks
use all paginated API entries independently of foreground search. Provider
receipts avoid automatically applying updates from a different known provider.

## Device results

The device downloaded actual service data and whole MPKs. Serial-triggered LVGL
button events exercised the real Activities; this is separate from a person's
touch confirmation and camera video.

| Case | Result and scope |
| --- | --- |
| Full compatibility catalog | Passed: 526 service entries, 530 merged entries including local apps; initial load 64623 ms |
| Rendered list and categories | Passed: All 530 rows, Utilities 384 rows, Installed 6 rows; counts matched rendered widgets and category membership |
| Official search UI | Passed: Settings / Search Store / Save, All category, visible CC Skill Smoke row and actual row-click navigation to AppDetail |
| Real package integrity / installation | Passed: CC Skill Smoke 1.0.0, revision 1; 3872 bytes, SHA256 44b63bb4af00613edea5ce01069aa58e3032a7dad81a7e350b263c35a75418b6 |
| Actual launch and return | Passed: CalculatorActivity opened, real button-matrix events produced `2 + 3 = 5`, then returned to AppDetail and AppStore |
| Official uninstall | Passed: user app removed and registry refreshed, followed by a fresh real-service install |
| Helper-module upgrade | Passed with local controlled transport: two apps ran v1 / 5, Update All installed v2, old helper modules were absent from sys.modules, and both actual Activities ran v2 / 105 |
| Missing launcher | Passed with controlled invalid revision 3: rejected before promotion; installed v1 and old helper remained |
| Background update notification | Passed with controlled catalog: two updates found, notification opened the official Updates view, Update All updated both apps |
| Fixture uninstall / transport cleanup | Passed: both helper applications and their receipts removed; real network transport restored |
| Hash mismatch protection | Passed: actual service package downloaded with a controlled wrong expected hash, rejected; installed main.py SHA256 unchanged |
| Controlled timeout | Passed: a delayed coroutine exceeded the framework deadline and showed TimeoutError with retry guidance; invalid earlier fixture runs are excluded |
| Actual WiFi offline prompt | Passed: WiFi disabled on device, install rejected with Offline guidance; Uninstall remained available |
| Actual network recovery | Passed: WiFi reconnected, real metadata and MPK requests completed, installation succeeded and the previous error description was cleared; stage and backup directories were empty |
| Actual HTTP 404 | Passed: obsolete sample detail returned HTTP 404; the detail screen offered retry and return |
| Real malformed packages | Passed: Danke failed the top-level identity check; Show Battery failed unsafe path validation; neither app was committed |
| Final state | Passed: running firmware SHA256 re-read and matched; online event loop alive, no framework overlay, test apps removed, controlled transport disabled, installation stage/backup empty |

The controlled apps are `com.freakstudio.storetest_upgrade` and
`com.freakstudio.storetest_peer`: 1.0.0/r1 to 1.1.0/r2. The Activity source stays
the same while the helper changes. Invalid 1.2.0/r3 has no main/launcher filter.
See `tests/fixtures/appstore_upystore/README.md` for exact reproduction. These are
not published uPyStore revisions and are not evidence of an online store upgrade.

The integration also requires an existing safe Python entrypoint, valid syntax
and classname, and both `main` and `launcher` in the same intent filter.
Installation checks cannot establish runtime dependency availability; launch was
tested separately. Hash/path/manifest failures do not replace the installed app.

## Automated checks

- 27 targeted CPython tests passed.
- 111 native MicroPython tests passed: update flow 62, async refresh 23,
  uninstall refresh 3, list build 3, ratings 15, installation safety 5.
- `make lint`, `make syntax-tests` and `git diff --check` passed.
- MPK layout and temporary extraction/install validation passed.
- The API summary checker reports the same 41 inherited official-code findings
  on the baseline and candidate, with no additional unknown symbols. These
  include fonts, SIZE_CONTENT, image descriptors and chained-call inference;
  the raw checker result is not reported as a pass. Runtime and native tests
  supply separate validation.
- The existing standalone version-check helper does not enumerate builtin apps;
  the builtin manifest bump from 1.5.0 to 1.5.1 was checked directly.

The precompiled desktop ELF failed during SDL initialization on the test host.
The native test runner uses a coherent source framework and an in-memory LVGL
display with the repository assertion self-check. It is not a full OS desktop
preview or a substitute for D-Shell testing.

## Service limitations and remaining acceptance

| Item | Exact request or action / required follow-up |
| --- | --- |
| Danke 0.1.0/r1 | https://upystore.io/api/v1/apps/com-freakstudio-danke/download?revision=1 ; publisher must restore the required application top-level directory |
| Show Battery 1.0.0/r1 | https://upystore.io/api/v1/apps/com-micropythonos-showbattery/download?revision=1 ; publisher must remove directory-external __MACOSX entries |
| Obsolete sample | https://upystore.io/api/v1/apps/io-kontinyu-upystore-sample returns 404; store maintainer must confirm removal, rename or republish |
| Calculator single files | https://upystore.io/api/v1/apps/com-example-cc-skill-smoke/rev/1/files/assets/main.py and https://upystore.io/api/v1/apps/com-example-cc-skill-smoke/rev/1/files/MANIFEST.JSON return 404; whole-MPK installation works |
| Firmware releases | https://upystore.io/api/v1/os/releases returns an empty published list; OTA is not accepted |
| Real online helper upgrade | Publisher must provide a trusted helper-containing application with two published revisions; controlled tests do not replace this case |
| New manual acceptance / video | Pending a fresh touch/scroll/install/open/uninstall confirmation and physical operation video for the official AppStore candidate; the prototype video is historical evidence |

uPyStore supplies no rating-submission contract, so those rating controls are
hidden rather than sending invented requests. Optional install-report and
device-profile APIs are not integrated in this scope; this is a client scope
limit, not a statement that the server lacks them. No version picker, downgrade,
camera/QR scan acceptance or OTA acceptance is claimed.

Serial logs include intermittent aiohttp response-header IndexError, timeout and
TLS failures. Retry succeeded for the healthy application. Not every low-level
failure has a uniquely identified URL; the remaining transport investigation is
not attributed entirely to OSUpdate. Current diagnostics identified TimeoutError
at `https://upystore.io/api/v1/apps?limit=100&page=3&q=` and OSError -29312 at
`https://upystore.io/api/v1/apps?limit=100&page=6&q=` during background checks,
plus a viewport icon timeout. Thus background version discovery is not proven
reliable across repeated live full-catalog checks. OSUpdate independently reproduced
`OSError: -29312` after reconnect, last checking
https://updates.micropythonos.org/osupdate_d_shell.json . OS/transport and update
source maintainers should review TLS/reconnect behavior. Initial full catalog
latency is approximately 65 seconds; successful HTTP status alone is not an
installation result.

Screenshots in the evidence bundle are actual RGB565 device framebuffer captures
and corresponding PNG conversions, not camera photographs or operation videos.
Raw serial logs, structured per-MPK case results, package hashes, controlled
fixtures and host regression outputs are retained with the delivery evidence.

Installation and reproduction: `docs/appstore-upystore.md`.
