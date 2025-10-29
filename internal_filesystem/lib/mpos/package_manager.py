import uos
import mpos.apps

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
                if uos.stat(dir_path)[0] & 0x4000:  # Verify directory exists
                    try:
                        for d in uos.listdir(dir_path):
                            full_path = f"{dir_path}/{d}"
                            print(f"full_path: {full_path}")
                            try:
                                if uos.stat(full_path)[0] & 0x4000:  # Check if it's a directory
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
