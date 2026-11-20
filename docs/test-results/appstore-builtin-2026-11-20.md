# Built-in AppStore and D-Shell verification, 2026-11-20

Checkpoint before upstream synchronization. The subsequent merge, new device
regression and contribution status are in `appstore-upstream-sync-2026-11-20.md`.
PR hold statements below describe this earlier checkpoint only.

This delivery directly modifies the existing builtin
`com.micropythonos.appstore` to connect its official UI and update management to
uPyStore. The independent 1.1.0 application is preserved as history and is not
installed alongside this version. The upstream PR remains on hold.

## What changed

AppStore **1.5.3** keeps the official identity, icon, flat module layout,
list/detail Activities, boot Service, categories, Installed/Updates, versions,
Open/Uninstall/Update, Update All, notifications, Settings and existing QR entry.
This project build defaults to uPyStore; BadgeHub remains selectable. This is
not a change to upstream defaults or evidence of upstream acceptance.

Both foreground and background use the same provider preference. Background
checks ignore search and compare revisions. Search does not clear updates or
start extra background checks. Store metadata is attached to App copies,
preserving AppManager's cached objects.

Size/SHA256, strict single application ZIP root and safe paths are retained.
Whole-directory staged replacement removes obsolete files and clears module
caches from the final installation's relative/absolute paths. Detected promotion
or receipt failures roll back. Power-loss safety is not claimed.

Entry validation requires one Activity intent filter containing both `main`
and `launcher`, valid entry paths/class identifiers and source syntax or a
compatible compiled header. Downloaded code is not executed during validation.
Runtime imports, dependencies and Activity initialization require a separate
launch check. Installation and launch are recorded separately.

Pause/destroy cancel page icon timers and release widgets. Callback tokens
handle actual LVGL timer wrappers. Late results cannot modify destroyed pages.
Update-manager start/stop is idempotent. An app-owned action/data intent keeps
notification navigation to Updates valid through persistence and dispatch.

Temporary installs use `cache/com.micropythonos.appstore/install`; receipts use
`prefs/com.micropythonos.appstore/receipts`. Earlier receipts migrate without
losing revision/source; uninstall removes both locations. No board/framework
source change or `/lib` overlay is used. Comments/docstrings and license remain.

## Target and artifact

| Item | Actual tested value |
| --- | --- |
| Device | D-Shell ESP32-S3 N16R8; 16 MB flash / 8 MB PSRAM |
| Display | 240 x 320 ST7789V / GT911; display SPI 80 MHz |
| Firmware | Existing MicroPythonOS 0.21.2 / API 0, not reflashed |
| Source | internal_filesystem/builtin/apps/com.micropythonos.appstore |
| Deployment | Same-fullname /apps update overrides older firmware builtin; no extra storefront |
| Release | 1.5.3, local unpublished revision 3, 34,071 bytes |
| MPK SHA256 | b436ce8aecb9502cdadfca08f07cb158e238aec64cc0f08bedcca0365f193e59 |
| Real store app | CC Skill Smoke 1.0.0 / revision 1; 3,872 bytes |
| Store MPK SHA256 | 44b63bb4af00613edea5ce01069aa58e3032a7dad81a7e350b263c35a75418b6 |

All nine installed file hashes match the MPK. A firmware rebuild would bundle
the modified builtin source normally; this test does not claim that rebuild.

## Checks completed

**42 CPython** cases and **130 native MicroPython** cases passed. Native counts:
update flow 62, async refresh 23, uninstall 3, list 3, ratings 15, install safety
10, owner lifecycle 5, builtin source/notification/search 9. Project lint,
MicroPython syntax, manifest, MPK layout/temporary install and diff checks passed.
The API checker still reports 41 inherited summary gaps plus one timer
return-type inference finding; it is not reported as passing. Real timer behavior
is checked on-device. Headless tests are not a complete SDL desktop preview.

| Physical operation on this MPK | Result |
| --- | --- |
| Original identity | 1.5.3, original fullname, upystore preference and nine file hashes match; independent app absent. |
| Real search/detail | Calculator search, official list/detail/version controls and isolated App objects pass. |
| Complete catalog/categories | Real All dropdown shows 529 merged entries; Utilities shows 384. Store objects are distinct from AppManager cached objects. |
| Uninstall | Official action removes calculator and receipt. |
| Real MPK installation | Device HTTPS download, expected size/SHA, installation and empty staging/backup pass. |
| Separate launch | Open starts CalculatorActivity; its real button matrix yields 2 + 3 = 5; return and widget cleanup pass. |
| Invalid launcher | Controlled r3 lacking main/launcher is rejected; installed v1/helper remain unchanged. |
| Renamed/deleted helpers | r1 actually imports an old-only helper. r2 renames its main helper and removes both old files. Update All clears files and caches; opening without reset executes renamed helper v2 / 105. |
| Same-name helper | A second app changes helper implementation; opening without reset executes v2 / 105. |
| Updates/notification | Actual background notification opens original AppStore Updates; both controlled apps update 1.0.0 to 1.1.0 and are subsequently uninstalled. |
| Wrong SHA | Real download with controlled wrong expected hash is rejected; installed main.py hash unchanged. |
| Timeout | Controlled timeout gives failure/retry and releases action; not attributed to an external server. |
| Network loss/recovery | Wi-Fi actually disabled; Offline prompt, reconnection and real reinstall retry pass. |
| Missing sample | Actual old sample details returns HTTP 404 with retry/back instruction. |
| Search/update isolation | Search leaves existing update state intact and triggers no extra update check; real search returns calculator again. |
| Final cleanup | Fixture transport restored, controlled apps removed, staging/backup empty, independent app absent, network/event loop alive; original Launcher restored. |

Local helper fixtures use injected metadata/download transport, restored after
testing. No device reset occurs between running old code, updating and running
new code. This is not a public uPyStore dual-revision upgrade. Images are actual
RGB565 device framebuffer captures, not camera recordings.

The user confirmed builtin 1.5.3 manual touch, scrolling, buttons, uninstall,
install, Open, 2 + 3 = 5 and return are normal. A matching new physical video
is pending. November 19 builtin
1.5.1 video and independent 1.1.0 manual feedback keep their original labels.

## Documentation and contribution review

Organization branch:
https://github.com/FreakStudioCN/MicroPythonOS/tree/feature/appstore-upystore

Base organization main: `8484908a5ceade80a7a5854925b85d662a3b480b`.
The inspected upstream revision was `4e34dd67de5f90707926282d3da23d0862c462f2`.
Existing AppStore/AppManager files had no intervening upstream change there.
Reviewed AGENTS.md, CONTRIBUTING.md, existing tests and these official documents:

- https://docs.micropythonos.com/apps/app-lifecycle/
- https://docs.micropythonos.com/apps/creating-apps/
- https://docs.micropythonos.com/apps/bundling-apps/
- https://docs.micropythonos.com/apps/appstore/
- https://docs.micropythonos.com/architecture/filesystem/
- https://docs.micropythonos.com/frameworks/app-manager/
- https://docs.micropythonos.com/frameworks/task-manager/
- https://docs.micropythonos.com/frameworks/service/
- https://docs.micropythonos.com/other/merge-checklist/

Kept flat builtin layout, migrated manifest categories, supported compiled entry
fallback, added regressions/CHANGELOG/reproduction steps and deterministic LF
packaging. No new board/framework requires a maintainer entry. Organization
commit/push, official PR submission and official merge are distinct states.

## Remaining issues and cooperation

| Item | Impact / owner / next step |
| --- | --- |
| Public two-revision helper app | Publisher must supply trusted revisions; controlled upgrade is passed, public upgrade pending. Plan scoped retest within one working day after readiness. |
| Background networking | Prior TLS -29312, timeout and HTTP-header IndexError remain. Foreground recovery is not proof of stable background discovery; OS/HTTP/TLS and store maintainers must investigate together. Repair date depends on root cause. |
| Danke / Show Battery | November 19 packages lacked required root / contained external __MACOSX respectively. Publishers must repair; no repair assumed and no client path checks relaxed. |
| 404s | Old sample still returns 404 on this device. Calculator single-file 404s are retained dated observations; tested whole MPK works. Store maintainer must confirm obsolete routes. |
| Scope limits | No supplied rating-write contract; optional install/profile reporting not enabled. Camera/QR, every-app compatibility, power-loss recovery and OTA not accepted; earlier firmware release list empty. |
| New video | Current builtin manual operations confirmed normal; matching new physical video pending, previous recordings remain historical. |
| Official PR | On hold by user instruction; neither submitted nor merged. |

Exact follow-up addresses:

- https://upystore.io/api/v1/apps?limit=100&page=6&q=
- https://upystore.io/api/v1/apps/io-kontinyu-upystore-sample
- https://upystore.io/api/v1/apps/com-freakstudio-danke/download?revision=1
- https://upystore.io/api/v1/apps/com-micropythonos-showbattery/download?revision=1
- https://upystore.io/api/v1/apps/com-example-cc-skill-smoke/rev/1/files/assets/main.py
- https://upystore.io/api/v1/apps/com-example-cc-skill-smoke/rev/1/files/MANIFEST.JSON
- https://upystore.io/api/v1/os/releases
- https://updates.micropythonos.org/osupdate_d_shell.json
