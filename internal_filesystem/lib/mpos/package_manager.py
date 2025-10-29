import os
import mpos.apps

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


class PackageManager():

    app_list = [] # list of App objects, sorted alphabetically by app.name, unique by full_name (com.example.appname)

    @classmethod
    def get_app_list(cls):
        if len(cls.app_list) == 0:
            cls.find_apps()
        return cls.app_list

    @classmethod
    def find_apps(cls):
        print("\n\n\nPackageManager finding apps...")
        seen_fullnames = set()
       # Check and collect subdirectories from existing directories
        apps_dir = "apps"
        apps_dir_builtin = "builtin/apps"

        # Check and collect unique subdirectories
        for dir_path in [apps_dir, apps_dir_builtin]:
            try:
                if os.stat(dir_path)[0] & 0x4000:  # Verify directory exists
                    try:
                        for d in os.listdir(dir_path):
                            full_path = f"{dir_path}/{d}"
                            print(f"full_path: {full_path}")
                            try:
                                if os.stat(full_path)[0] & 0x4000:  # Check if it's a directory
                                    fullname = d
                                    if fullname not in seen_fullnames:  # Avoid duplicates
                                        seen_fullnames.add(fullname)
                                        app = mpos.apps.parse_manifest(full_path)
                                        cls.app_list.append(app)
                                        print(f"added app {app}")
                            except Exception as e:
                                print(f"PackageManager: stat of {full_path} got exception: {e}")
                    except Exception as e:
                        print(f"PackageManager: listdir of {dir_path} got exception: {e}")
            except Exception as e:
                print(f"PackageManager: stat of {dir_path} got exception: {e}")

        # Sort apps alphabetically by app.name
        cls.app_list.sort(key=lambda x: x.name.lower())  # Case-insensitive sorting by name

    @staticmethod
    def uninstall_app(app_fullname):
        try:
            import shutil
            shutil.rmtree(f"apps/{app_fullname}") # never in builtin/apps because those can't be uninstalled
            # TODO: also remove it from the app_list
        except Exception as e:
            print(f"Removing app_folder {app_folder} got error: {e}")

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
        installed_app=None
        if PackageManager.is_installed_by_path(appdir):
            print(f"{appdir} found, getting version...")
            installed_app = mpos.apps.parse_manifest(appdir) # probably no need to re-parse the manifest
        elif PackageManager.is_installed_by_path(builtinappdir):
            print(f"{builtinappdir} found, getting version...")
            installed_app = mpos.apps.parse_manifest(builtinappdir) # probably no need to re-parse the manifest
        if not installed_app or installed_app.version == "0.0.0": # special case, if the installed app doesn't have a version number then there's no update
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

