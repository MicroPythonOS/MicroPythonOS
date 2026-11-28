# Optional uPyStore backend for AppStore

The builtin AppStore can use upystore.io while retaining BadgeHub as its default.
Select **uPyStore** in Store Source; existing explicit choices are preserved.
The app keeps its original identity, activities, boot service and user interface.

## Preserved behavior

- The official list and detail screens, viewport icon loading and placeholders.
- Category filters, Installed and Updates lists, installed/available versions,
  Open, Uninstall and Update actions.
- Sequential Update All, the boot update service and update notifications.
- Icon, work-in-progress and notification preferences; the existing QR entry.
- BadgeHub remains the official default. Select uPyStore in Store Source;
  existing explicit source preferences are retained.

Store Source and Search Store are added to the existing settings UI. Foreground
views and the background update service read the same source preference. A search
never restricts background update discovery or clears pending update state.
Only changing the actual source resets provider-specific results. The latter fetches every API page,
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
- uPyStore metadata, icons and package requests share an application-local queue to
  limit concurrent TLS work. JSON collection is bounded. The large compatibility
  catalog has a longer deadline than individual metadata requests.
- uPyStore packages require matching size/SHA256, a matching top-level app
  directory, safe ZIP paths and sufficient extraction space. `__MACOSX` outside
  the app directory is rejected, not silently removed.
- Extraction is staged. Identity/version, Activity paths, Python syntax, class
  name syntax and a single intent filter containing both `main` and `launcher`
  are checked before promotion. Compiled `.mpy` entrypoints and `.py` manifest
  entries backed by `.mpy` files retain AppManager's import behavior; compiled
  headers are checked without executing downloaded code. Runtime ABI,
  dependencies and Activity initialization
  are checked separately by actually launching the app.
- Promotion clears cached modules from the final application's relative and
  absolute paths and refreshes AppManager's registry. Receipt-write/promotion
  exceptions restore the previous installation. This is not a claim of
  power-loss-safe filesystem transactions.
- Uninstall checks that the user installation was removed before dropping its
  receipt. Failed requests restore usable actions and show a retry instruction.
- Downloads and staging use `cache/com.micropythonos.appstore/install`; receipts
  use `prefs/com.micropythonos.appstore/receipts`. Receipts from the earlier local
  `data/appstore/receipts` layout remain readable and migrate on access. Uninstall
  removes both receipt locations to prevent an old receipt from reappearing.
  A pending legacy install backup blocks another install until recovery.
- Pausing a detail page cancels its pending icon timer. Destroyed pages release
  widget references; late network results can update data without touching
  destroyed widgets. Installation work may finish safely after leaving its page.
- On firmware exposing the current asynchronous extractor, the verified archive
  is staged with the framework's `StreamingUnzip.feed_async` and extent writer.
  The archive is closed around a storage reservation and reopened at its saved
  position, matching the upstream defragmentation constraint. The detail page's
  storage-progress callback is retained and checks foreground state. Older
  firmware falls back to its existing `AppManager.install_mpk` API.

There is no `/lib/mpos` overlay and no board or global OS source modification.
Source changes are in `internal_filesystem/builtin/apps/com.micropythonos.appstore`.
On-device validation installs a same-fullname update under `/apps`, which takes
precedence over the firmware's older built-in copy. It is the existing AppStore
entry, not a separately installed storefront. A firmware rebuild would bundle
these sources in the normal built-in archive.

## Build and install the development MPK

From the repository root, using host Python:

```text
python scripts/package_appstore.py --output-dir tmp/appstore-standards-release --revision 4
```

The script writes `com.micropythonos.appstore_r4.mpk` and `release.json`, including
package and per-file SHA256 values. The local revision is not a store publication.
It preserves the official flat app layout and packages only this builtin app.

Upload the MPK to the device's `/data` using the existing WebREPL file transfer
or your normal MPOS file-transfer workflow. Keep the running asyncio REPL alive;
do not repeatedly interrupt it with raw-REPL attach commands. In the running REPL:

```python
from mpos import AppManager
AppManager.install_mpk('/data/com.micropythonos.appstore_r4.mpk',
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

Existing explicit uPyStore choices stay selected. Fresh configurations and
invalid stored source values use BadgeHub, matching the official default.
Earlier unpublished project builds used an implicit uPyStore default; if such
a build never saved a choice, select uPyStore once in Settings after upgrading.

## Regression commands

```text
python tests/cpython_appstore_upystore.py
python tests/cpython_appstore_review.py
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
live-store download/install evidence.

## Service and acceptance limits

- uPyStore has no supplied rating-submission contract. Its rating controls are
  hidden; `stars_count` is not treated as an average rating. BadgeHub's existing
  rating/reporting path is retained.
- Optional uPyStore install-report and device-profile telemetry are not integrated
  in this scope; those APIs exist and are not described as unsupported by the server.
- The existing QR workflow is retained. D-Shell has no configured camera; camera
  scanning and support for new uPyStore web-link QR formats are not accepted here.
- No downgrade/version picker or OTA acceptance is claimed. OSUpdate remains
  independent of the application store source.
- Missing entries and malformed packages fail with a retry instruction; healthy
  whole-MPK installation does not depend on individual-file download endpoints.
  Client path validation remains strict, including directory-external __MACOSX.
- A live store upgrade between two published helper-containing revisions still
  requires a suitable publisher-provided sample. Local controlled upgrades are
  not reported as that live service test.
