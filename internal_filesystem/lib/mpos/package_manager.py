import os

from mpos.app.app import App
from mpos.app.activities.view import ViewActivity
from mpos.app.activities.share import ShareActivity

try:
    import zipfile
except ImportError:
    print("import zipfile failed, installation won't work!")

'''
Initialized at boot.
Typical users: appstore, launcher

Allows users to:
- list installed apps (including all app data like icon, version, etc)
- install app from .zip file
- uninstall app
- check if an app is installed + which version

Why this exists:
- the launcher was listing installed apps, reading them, loading the icons, starting apps
- the appstore was also listing installed apps, reading them, (down)loading the icons, starting apps
- other apps might also want to do so
Previously, some functionality was deduplicated into apps.py
But the main issue was that the list of apps was built by both etc.

Question: does it make sense to cache the database?
=> No, just read/load them at startup and keep the list in memory, and load the icons at runtime.

'''

class PackageManager:

    APP_REGISTRY = {
        "view": [ViewActivity],
        "share": [ShareActivity]
    }

    """Registry of all discovered apps.

    * PackageManager.get_app_list()          -> list of App objects (sorted by name)
    * PackageManager[fullname]               -> App (raises KeyError if missing)
    * PackageManager.get(fullname)           -> App or None
    """

    # --------------------------------------------------------------------- #
    # internal storage
    # --------------------------------------------------------------------- #
    _app_list = []                     # sorted by app.name
    _by_fullname = {}                  # fullname -> App

    # --------------------------------------------------------------------- #
    # public list access (kept for backward compatibility)
    # --------------------------------------------------------------------- #
    @classmethod
    def get_app_list(cls):
        if not cls._app_list:
            cls.refresh_apps()
        return cls._app_list

    # --------------------------------------------------------------------- #
    # dict-style lookup:  PackageManager["com.example.myapp"]
    # --------------------------------------------------------------------- #
    def __class_getitem__(cls, fullname):
        try:
            return cls._by_fullname[fullname]
        except KeyError:
            raise KeyError("No app with fullname='{}'".format(fullname))

    # --------------------------------------------------------------------- #
    # safe lookup:  PackageManager.get("com.example.myapp") -> App or None
    # --------------------------------------------------------------------- #
    @classmethod
    def get(cls, fullname):
        return cls._by_fullname.get(fullname)

    # --------------------------------------------------------------------- #
    # Clear everything – useful when you want to force a full rescan
    # --------------------------------------------------------------------- #
    @classmethod
    def clear(cls):
        """Empty the internal caches.  Call ``get_app_list()`` afterwards to repopulate."""
        cls._app_list = []
        cls._by_fullname = {}

    # --------------------------------------------------------------------- #
    # discovery & population
    # --------------------------------------------------------------------- #
    @classmethod
    def refresh_apps(cls):
        print("PackageManager finding apps...")

        cls.clear()                     # <-- this guarantees both containers are empty
        seen = set()                     # avoid processing the same fullname twice
        apps_dir         = "apps"
        apps_dir_builtin = "builtin/apps"

        for base in (apps_dir, apps_dir_builtin):
            try:
                # ---- does the directory exist? --------------------------------
                st = os.stat(base)
                if not (st[0] & 0x4000):          # 0x4000 = directory bit
                    continue

                # ---- iterate over immediate children -------------------------
                for name in os.listdir(base):
                    full_path = "{}/{}".format(base, name)

                    # ---- is it a directory? ---------------------------------
                    try:
                        st = os.stat(full_path)
                        if not (st[0] & 0x4000):
                            continue
                    except Exception as e:
                        print("PackageManager: stat of {} got exception: {}".format(full_path, e))
                        continue

                    fullname = name

                    # ---- skip duplicates ------------------------------------
                    if fullname in seen:
                        continue
                    seen.add(fullname)

                    # ---- parse the manifest ---------------------------------
                    try:
                        app = App.from_manifest(full_path)
                    except Exception as e:
                        print("PackageManager: parsing {} failed: {}".format(full_path, e))
                        continue

                    # ---- store in both containers ---------------------------
                    cls._app_list.append(app)
                    cls._by_fullname[fullname] = app
                    print("added app {}".format(app))

            except Exception as e:
                print("PackageManager: handling {} got exception: {}".format(base, e))

        # ---- sort the list by display name (case-insensitive) ------------
        cls._app_list.sort(key=lambda a: a.name.lower())

    @staticmethod
    def uninstall_app(app_fullname):
        try:
            import shutil
            shutil.rmtree(f"apps/{app_fullname}") # never in builtin/apps because those can't be uninstalled
        except Exception as e:
            print(f"Removing app_folder {app_folder} got error: {e}")
        PackageManager.refresh_apps()

    @staticmethod
    def install_mpk(temp_zip_path, dest_folder):
        try:
            # Step 2: Unzip the file
            print("Unzipping it to:", dest_folder)
            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                zip_ref.extractall(dest_folder)
            print("Unzipped successfully")
            # Step 3: Clean up
            os.remove(temp_zip_path)
            print("Removed temporary .mpk file")
        except Exception as e:
            print(f"Unzip and cleanup failed: {e}")
            # Would be good to show error message here if it fails...
        PackageManager.refresh_apps()

    @staticmethod
    def compare_versions(ver1: str, ver2: str) -> bool:
        """Compare two version numbers (e.g., '1.2.3' vs '4.5.6').
        Returns True if ver1 is greater than ver2, False otherwise."""
        print(f"Comparing versions: {ver1} vs {ver2}")
        v1_parts = [int(x) for x in ver1.split('.')]
        v2_parts = [int(x) for x in ver2.split('.')]
        print(f"Version 1 parts: {v1_parts}")
        print(f"Version 2 parts: {v2_parts}")
        for i in range(max(len(v1_parts), len(v2_parts))):
            v1 = v1_parts[i] if i < len(v1_parts) else 0
            v2 = v2_parts[i] if i < len(v2_parts) else 0
            print(f"Comparing part {i}: {v1} vs {v2}")
            if v1 > v2:
                print(f"{ver1} is greater than {ver2}")
                return True
            if v1 < v2:
                print(f"{ver1} is less than {ver2}")
                return False
        print(f"Versions are equal or {ver1} is not greater than {ver2}")
        return False

    @staticmethod
    def is_builtin_app(app_fullname):
        return PackageManager.is_installed_by_path(f"builtin/apps/{app_fullname}")

    @staticmethod
    def is_overridden_builtin_app(app_fullname):
        return PackageManager.is_installed_by_path(f"apps/{app_fullname}") and PackageManager.is_installed_by_path(f"builtin/apps/{app_fullname}")

    @staticmethod
    def is_update_available(app_fullname, new_version):
        appdir = f"apps/{app_fullname}"
        builtinappdir = f"builtin/apps/{app_fullname}"
        installed_app=PackageManager.get(app_fullname)
        if not installed_app:
            return False
        return PackageManager.compare_versions(new_version, installed_app.version)

    @staticmethod
    def is_installed_by_path(dir_path):
        try:
            if os.stat(dir_path)[0] & 0x4000:
                print(f"is_installed_by_path: {dir_path} found, checking manifest...")
                manifest = f"{dir_path}/META-INF/MANIFEST.JSON"
                if os.stat(manifest)[0] & 0x8000:
                    return True
        except OSError:
            print(f"is_installed_by_path got OSError for {dir_path}")
            pass # Skip if directory or manifest doesn't exist
        return False

    @staticmethod
    def is_installed_by_name(app_fullname):
        print(f"Checking if app {app_fullname} is installed...")
        return PackageManager.is_installed_by_path(f"apps/{app_fullname}") or PackageManager.is_installed_by_path(f"builtin/apps/{app_fullname}")


