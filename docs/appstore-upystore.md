# Official AppStore integration with uPyStore

This branch adapts `com.micropythonos.appstore`, retaining its Activity, boot
Service and UI. It does not ship the earlier standalone uPyStore prototype.
The development AppStore version is **1.5.1**, based on organization main
`8484908a5ceade80a7a5854925b85d662a3b480b`. This is a fork build, not an
upstream-published AppStore release.

## Preserved behavior

- The official list and detail screens, viewport icon loading and placeholders.
- Category filters, Installed and Updates lists, installed/available versions,
  Open, Uninstall and Update actions.
- Sequential Update All, the boot update service and update notifications.
- Icon, work-in-progress and notification preferences; the existing QR entry.
- BadgeHub remains selectable in Settings. uPyStore is this integration's default.

Store Source and Search Store are added to the existing settings UI. Foreground
views and the background update service read the same source preference. A search
never restricts background update discovery. The latter fetches every API page,
including revisions, so an updated revision of the same semantic version can be
noticed. Receipts prevent automatic updates across a known change of provider.

## API and install behavior

- The ordinary catalog uses `https://upystore.io/app_index.json`; search and
  revision-aware update discovery use `/api/v1/apps` and follow pagination.
- `fullname` identifies an installation; the distinct API `slug` routes requests.
  Relative icon/download URLs are resolved against the HTTPS store origin.
- Details use `/api/v1/apps/{slug}` and its returned `versions` metadata. The
  version matching the current revision supplies the size, SHA256 and MPK URL.
- Downloads use the complete revision-specific MPK, not individual-file endpoints.
- Store metadata, icons and package requests share an application-local queue to
  limit concurrent TLS work. JSON collection is bounded. The large compatibility
  catalog has a longer deadline than individual metadata requests.
- uPyStore packages require matching size/SHA256, a matching top-level app
  directory, safe ZIP paths and sufficient extraction space. `__MACOSX` outside
  the app directory is rejected, not silently removed.
- Extraction is staged. Identity/version, Activity paths, Python syntax, class
  name syntax and a single intent filter containing both `main` and `launcher`
  are checked before promotion. Runtime dependencies and Activity initialization
  are checked separately by actually launching the app.
- Promotion clears cached modules from the final application's relative and
  absolute paths and refreshes AppManager's registry. Receipt-write/promotion
  exceptions restore the previous installation. This is not a claim of
  power-loss-safe filesystem transactions.
- Uninstall checks that the user installation was removed before dropping its
  receipt. Failed requests restore usable actions and show a retry instruction.

There is no `/lib/mpos` overlay and no board or global OS source modification.

## Build and install the development MPK

From the repository root, using host Python:

```text
python scripts/package_appstore.py --output-dir tmp/appstore-release --revision 1
```

The script writes `com.micropythonos.appstore_r1.mpk` and `release.json`, including
package and per-file SHA256 values. The local revision is not a store publication.
It preserves the official flat app layout and packages only this builtin app.

Upload the MPK to the device's `/data` using the existing WebREPL file transfer
or your normal MPOS file-transfer workflow. Keep the running asyncio REPL alive;
do not repeatedly interrupt it with raw-REPL attach commands. In the running REPL:

```python
from mpos import AppManager
AppManager.install_mpk('/data/com.micropythonos.appstore_r1.mpk',
                       '/apps/com.micropythonos.appstore')
import machine
machine.reset()
```

A hard restart is required so the updated boot Service and all app-local modules
are loaded together. The `/apps` override takes precedence over the frozen builtin.
Open **AppStore**, choose uPyStore under Store Source, and select **All** in the
category dropdown. The official store initially shows Installed; remote search
results remain subject to the selected category. Under Settings, use Search Store
to search for `CC Skill Smoke`, save, and return to the list. Install, Open,
calculate `2 + 3 = 5`, return and Uninstall.
Check installation and launch separately. Never copy this app into `/lib`.

## Regression commands

```text
python tests/cpython_appstore_upystore.py
make lint
make syntax-tests
make check-app-versions ARGS=--changed
```

The native MicroPython tests can run without SDL window initialization:

```text
python scripts/test_appstore_headless.py --binary lvgl_micropython/build/lvgl_micropy_unix
```

This uses the repository's assertion self-check and LVGL with an in-memory display.
It is a MicroPython unit regression run, not a physical display test or a complete
OS desktop preview. Logs and results go to `tmp/appstore-native-regressions`.

See `tests/fixtures/appstore_upystore/README.md` for a reproducible helper-module
upgrade and invalid-launcher fixture. Controlled fixtures are kept separate from
live-store download/install evidence. See the dated test report under
`docs/test-results` for actual scope and remaining work.

## Service and acceptance limits

- uPyStore has no supplied rating-submission contract. Its rating controls are
  hidden; `stars_count` is not treated as an average rating. BadgeHub's existing
  rating/reporting path is retained.
- Optional uPyStore install-report and device-profile telemetry are not integrated
  in this scope; those APIs exist and are not described as unsupported by the server.
- The existing QR workflow is retained. D-Shell has no configured camera; camera
  scanning and support for new uPyStore web-link QR formats are not accepted here.
- No rollback/version picker or OTA acceptance is claimed. The firmware release
  API was empty. The OSUpdate service remains independent.
- The obsolete sample and some calculator single-file endpoints return 404.
  Healthy whole-MPK installation does not depend on them.
- Danke and Show Battery still require publisher-side package repairs. A healthy
  calculator and controlled fixtures do not establish compatibility of all apps.
- A live store upgrade between two published helper-containing revisions still
  requires a suitable publisher-provided sample. Local controlled upgrades are
  not reported as that live service test.
