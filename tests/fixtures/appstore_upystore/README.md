# Controlled AppStore upgrade fixtures

These are local acceptance fixtures, not published uPyStore applications.
`device_transport.py` temporarily substitutes responses for the compatibility
catalog, paginated API list and the two test app routes. Other requests pass
through. Do not leave it installed after testing.

Build from the repository root:

```text
python tests/fixtures/appstore_upystore/build_fixtures.py
```

The output is `tmp/appstore-fixtures/fixture-bundle.zip`, six MPKs and a metadata
file containing package SHA256 values. Each of the two apps has:

| Revision | Version | Helper result | Purpose |
| --- | --- | --- | --- |
| 1 | 1.0.0 | `v1 / 5` | Install and open the old helper |
| 2 | 1.1.0 | `v2 / 105` | Update and prove the new helper was imported |
| 3 | 1.2.0 | `v3 / 205` | Invalid package without a main/launcher filter |

The Activity source is identical between revisions of each app; the helper module
changes. The two helper module names are distinct. Packages have deterministic
entries and the required application root directory.

Upload `fixture-bundle.zip` to `/data`. In the running MPOS REPL:

```python
import sys
from mpos import AppManager, SharedPreferences
AppManager.install_mpk('/data/fixture-bundle.zip', '/data/appstore-test')
sys.path.insert(0, '/data/appstore-test')
import device_transport
SharedPreferences('com.micropythonos.appstore').edit().put_string('store_query', '').commit()
device_transport.install()
```

1. Open AppStore and select All. Install `TEST Helper upgrade` and
   `TEST Helper peer`. Open each: both must display `TEST helper v1 / 5`.
2. Return from the apps to AppStore. Set `device_transport.revision = 3`, reopen
   the store and try the upgrade app's Update action. The main/launcher check must
   reject it. Installed version, helper code and receipt must remain at revision 1.
3. Close AppStore, set `device_transport.revision = 2`, then request a background
   check with `AppUpdateManager.get_instance().check_for_updates_now()` from
   `appstore_core`. With notifications enabled, verify that two updates are found.
4. Open the update notification, verify the Updates category, and use Update All.
   Both apps must become version 1.1.0. Open each again: both must show
   `TEST helper v2 / 105`. Check the actual Activity output, not just the manifest.
5. Uninstall both through AppStore. Their user app directories and receipts must
   disappear. No former helper module should remain in `sys.modules`.

Always restore the real transport, including after a failed test:

```python
device_transport.uninstall()
sys.path.remove('/data/appstore-test')
```

Reopen AppStore and fetch a real catalog/detail to verify that normal service
requests are restored. Test-only files live under `/data/appstore-test`; they are
not included in the AppStore MPK and no framework files are shadowed.
