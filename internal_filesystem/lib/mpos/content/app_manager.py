import os

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

class AppManager:

    _registry = {}          # action → [ActivityClass, ...]

    @classmethod
    def register_activity(cls, action, activity_cls):
        """Called by each activity module to register itself."""
        if action not in cls._registry:
            cls._registry[action] = []
        if activity_cls not in cls._registry[action]:
            cls._registry[action].append(activity_cls)

    @classmethod
    def resolve_activity(cls, intent):
        """Return list of Activity classes that handle the intent.action."""
        return cls._registry.get(intent.action, [])

    @classmethod
    def query_intent_activities(cls, intent):
        """Same as resolve_activity – more Android-like name."""
        return cls.resolve_activity(intent)

    """Registry of all discovered apps.

    * AppManager.get_app_list()          -> list of App objects (sorted by name)
    * AppManager[fullname]               -> App (raises KeyError if missing)
    * AppManager.get(fullname)           -> App or None
    """

    _app_list = []                     # sorted by app.name
    _by_fullname = {}                  # fullname -> App

    @classmethod
    def get_app_list(cls):
        if not cls._app_list:
            cls.refresh_apps()
        return cls._app_list

    def __class_getitem__(cls, fullname):
        try:
            return cls._by_fullname[fullname]
        except KeyError:
            raise KeyError("No app with fullname='{}'".format(fullname))

    @classmethod
    def get(cls, fullname):
        if not cls._app_list:
            cls.refresh_apps()
        return cls._by_fullname.get(fullname)

    @classmethod
    def get_launcher(cls):
        for app in cls.get_app_list():
            if app.is_valid_launcher():
                print(f"Found launcher {app.fullname}")
                return app

    @classmethod
    def clear(cls):
        """Empty the internal caches.  Call ``get_app_list()`` afterwards to repopulate."""
        cls._app_list = []
        cls._by_fullname = {}

    @classmethod
    def refresh_apps(cls):
        print("AppManager finding apps...")

        cls.clear()                     # <-- this guarantees both containers are empty
        seen = set()                     # avoid processing the same fullname twice
        apps_dir         = "apps"
        apps_dir_builtin = "builtin/apps"

        for base in (apps_dir, apps_dir_builtin): # added apps override builtin apps
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
                        print("AppManager: stat of {} got exception: {}".format(full_path, e))
                        continue

                    fullname = name

                    # ---- skip duplicates ------------------------------------
                    if fullname in seen:
                        continue
                    seen.add(fullname)

                    # ---- parse the manifest ---------------------------------
                    try:
                        from ..app.app import App
                        app = App.from_manifest(full_path)
                    except Exception as e:
                        print("AppManager: parsing {} failed: {}".format(full_path, e))
                        continue

                    # ---- store in both containers ---------------------------
                    cls._app_list.append(app)
                    cls._by_fullname[fullname] = app
                    print("added app {}".format(app))

            except Exception as e:
                print("AppManager: handling {} got exception: {}".format(base, e))

        # ---- sort the list by display name (case-insensitive) ------------
        cls._app_list.sort(key=lambda a: a.name.lower())

    @staticmethod
    def uninstall_app(app_fullname):
        try:
            import shutil
            shutil.rmtree(f"apps/{app_fullname}") # never in builtin/apps because those can't be uninstalled
        except Exception as e:
            print(f"Removing app_folder {app_folder} got error: {e}")
        AppManager.refresh_apps()

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
        AppManager.refresh_apps()

    @staticmethod
    def compare_versions(ver1: str, ver2: str) -> bool:
        """Compare two version numbers (e.g., '1.2.3' vs '4.5.6').
        Returns True if ver1 is greater than ver2, False otherwise.
        Invalid or empty version numbers also result in False."""
        print(f"Comparing versions: {ver1} vs {ver2}")
        try:
            v1_parts = [int(x) for x in ver1.split('.')]
            v2_parts = [int(x) for x in ver2.split('.')]
        except ValueError as e:
            print(f"Invalid input, got error: {e}")
            return False
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
        return AppManager.is_installed_by_path(f"builtin/apps/{app_fullname}")

    @staticmethod
    def is_overridden_builtin_app(app_fullname):
        return AppManager.is_installed_by_path(f"apps/{app_fullname}") and AppManager.is_installed_by_path(f"builtin/apps/{app_fullname}")

    @staticmethod
    def is_update_available(app_fullname, new_version):
        appdir = f"apps/{app_fullname}"
        builtinappdir = f"builtin/apps/{app_fullname}"
        installed_app=AppManager.get(app_fullname)
        if not installed_app:
            return False
        return AppManager.compare_versions(new_version, installed_app.version)

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
        return AppManager.is_installed_by_path(f"apps/{app_fullname}") or AppManager.is_installed_by_path(f"builtin/apps/{app_fullname}")

    @staticmethod
    def execute_script(script_source, is_file, classname, cwd=None):
        """Run the script in the current thread. Returns True if successful."""
        import utime # for timing read and compile
        import lvgl as lv
        import mpos.ui
        import _thread
        thread_id = _thread.get_ident()
        compile_name = 'script' if not is_file else script_source
        print(f"Thread {thread_id}: executing script with cwd: {cwd}")
        try:
            if is_file:
                print(f"Thread {thread_id}: reading script from file {script_source}")
                with open(script_source, 'r') as f: # No need to check if it exists as exceptions are caught
                    start_time = utime.ticks_ms()
                    script_source = f.read()
                    read_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                    print(f"execute_script: reading script_source took {read_time}ms")
            script_globals = {
                'lv': lv,
                '__name__': "__main__", # in case the script wants this
                '__file__': compile_name
            }
            print(f"Thread {thread_id}: starting script")
            import sys
            path_before = sys.path[:]  # Make a copy, not a reference
            if cwd:
                sys.path.append(cwd)
            try:
                start_time = utime.ticks_ms()
                compiled_script = compile(script_source, compile_name, 'exec')
                compile_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                print(f"execute_script: compiling script_source took {compile_time}ms")
                start_time = utime.ticks_ms()
                exec(compiled_script, script_globals)
                end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                print(f"apps.py execute_script: exec took {end_time}ms")
                # Introspect globals
                classes = {k: v for k, v in script_globals.items() if isinstance(v, type)}
                functions = {k: v for k, v in script_globals.items() if callable(v) and not isinstance(v, type)}
                variables = {k: v for k, v in script_globals.items() if not callable(v)}
                print("Classes:", classes.keys()) # This lists a whole bunch of classes, including lib/mpos/ stuff
                print("Functions:", functions.keys())
                print("Variables:", variables.keys())
                main_activity = script_globals.get(classname)
                if main_activity:
                    from ..app.activity import Activity
                    from .intent import Intent
                    start_time = utime.ticks_ms()
                    Activity.startActivity(None, Intent(activity_class=main_activity))
                    end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                    print(f"execute_script: Activity.startActivity took {end_time}ms")
                else:
                    print(f"Warning: could not find app's main_activity {classname}")
                    return False
            except Exception as e:
                print(f"Thread {thread_id}: exception during execution:")
                sys.print_exception(e)
                return False
            finally:
                # Always restore sys.path, even if we return early or raise an exception
                print(f"Thread {thread_id}: script {compile_name} finished, restoring sys.path from {sys.path} to {path_before}")
                sys.path = path_before
            return True
        except Exception as e:
            print(f"Thread {thread_id}: error:")
            tb = getattr(e, '__traceback__', None)
            traceback.print_exception(type(e), e, tb)
            return False

    @staticmethod
    def start_app(fullname):
        """Start an app by fullname. Returns True if successful."""
        import mpos.ui
        mpos.ui.set_foreground_app(fullname)
        import utime
        start_time = utime.ticks_ms()
        app = AppManager.get(fullname)
        if not app:
            print(f"Warning: start_app can't find app {fullname}")
            return
        if not app.installed_path:
            print(f"Warning: start_app can't start {fullname} because no it doesn't have an installed_path")
            return
        entrypoint = "assets/main.py"
        classname = "Main"
        if not app.main_launcher_activity:
            print(f"WARNING: app {fullname} doesn't have a main_launcher_activity, defaulting to class {classname} in {entrypoint}")
        else:
            entrypoint = app.main_launcher_activity.get('entrypoint')
            classname = app.main_launcher_activity.get("classname")
        result = AppManager.execute_script(app.installed_path + "/" + entrypoint, True, classname, app.installed_path + "/assets/")
        # Launchers have the bar, other apps don't have it
        if app.is_valid_launcher():
            mpos.ui.topmenu.open_bar()
        else:
            mpos.ui.topmenu.close_bar()
        end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
        print(f"start_app() took {end_time}ms")
        return result

    @staticmethod
    def restart_launcher():
        """Restart the launcher by stopping all activities and starting the launcher app."""
        import mpos.ui
        print("restart_launcher")
        # Stop all apps
        mpos.ui.remove_and_stop_all_activities()
        # No need to stop the other launcher first, because it exits after building the screen
        return AppManager.start_app(AppManager.get_launcher().fullname)
