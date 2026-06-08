import os

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

import logging
logger = logging.getLogger(__name__)

class AppManager:

    _registry = {}          # action → [ActivityClass, ...]
    _service_registry = {}  # action → [(fullname_or_None, ServiceClass), ...]

    @classmethod
    def register_activity(cls, action, activity_cls):
        """Called by each activity module to register itself."""
        if action not in cls._registry:
            cls._registry[action] = []
        if activity_cls not in cls._registry[action]:
            cls._registry[action].append(activity_cls)

    @classmethod
    def register_service(cls, action, service_cls, fullname=None):
        if action not in cls._service_registry:
            cls._service_registry[action] = []
        entry = (fullname, service_cls)
        if entry not in cls._service_registry[action]:
            cls._service_registry[action].append(entry)

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
                if __debug__: logger.debug("Found launcher %s", app.fullname)
                return app

    @classmethod
    def clear(cls):
        """Empty the internal caches.  Call ``get_app_list()`` afterwards to repopulate."""
        cls._app_list = []
        cls._by_fullname = {}

    @classmethod
    def refresh_apps(cls):
        if __debug__: logger.debug("Finding apps...")

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
                        logger.error("stat of %s got exception: %s", full_path, e)
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
                        logger.error("parsing %s failed: %s", full_path, e)
                        continue

                    # ---- store in both containers ---------------------------
                    cls._app_list.append(app)
                    cls._by_fullname[fullname] = app

            except Exception as e:
                logger.error("handling %s got exception: %s", base, e)

        # ---- sort the list by display name (case-insensitive) ------------
        cls._app_list.sort(key=lambda a: a.name.lower())

    @staticmethod
    async def download_and_install_package(download_url, fullname, download_url_size=None, progress_callback=None):
        """Download an .mpk package and install it into apps/<fullname>.

        The download is fed directly into a streaming ZIP extractor so no
        temporary file is written to storage.  Extraction starts immediately
        once the first chunk arrives, and the archive is validated against the
        strict MPK spec (single top-level dir matching ``fullname``).

        Raises an exception on failure so the caller can handle UI feedback.
        Returns True on success.
        """
        import os
        import shutil
        from ..net.download_manager import DownloadManager
        from .streaming_unzip import StreamingUnzip

        dest_folder = f"apps/{fullname}"

        # Step 1: Remove any existing (possibly partial) install or symlink
        try:
            st = os.stat(dest_folder)
            if st[0] & 0x4000:
                shutil.rmtree(dest_folder)
                if __debug__: logger.debug("Removed existing folder: %s", dest_folder)
            else:
                os.remove(dest_folder)
                if __debug__: logger.debug("Removed existing file: %s", dest_folder)
        except OSError:
            pass
        try:
            os.remove(dest_folder)
            if __debug__: logger.debug("Removed symlink: %s", dest_folder)
        except OSError:
            pass

        if __debug__: logger.debug("streaming download+install %s -> %s", download_url, dest_folder)

        extractor = StreamingUnzip(
            dest_folder,
            expected_app_name=fullname,
            free_space_limit=lambda req: AppManager._check_free_space(".", req),
        )

        async def _chunk_callback(chunk):
            extractor.feed(chunk)

        try:
            result = await DownloadManager.download_url(
                download_url,
                chunk_callback=_chunk_callback,
                total_size=download_url_size,
                progress_callback=progress_callback,
            )
        except Exception as e:
            logger.error("download exception for %s: %s", fullname, e)
            try:
                shutil.rmtree(dest_folder)
            except Exception:
                pass
            raise RuntimeError(f"Download failed for {fullname}: {e}")

        if result is not True:
            try:
                shutil.rmtree(dest_folder)
            except Exception:
                pass
            raise RuntimeError(f"Download failed for {fullname}")

        try:
            extractor.finish()
        except Exception as e:
            logger.error("install exception for %s: %s", fullname, e)
            try:
                shutil.rmtree(dest_folder)
            except Exception:
                pass
            raise RuntimeError(f"Download failed for {fullname}: {e}")

        if __debug__: logger.debug("installed %s successfully", fullname)
        return True

    @staticmethod
    def _check_free_space(path, required_bytes):
        """Raise RuntimeError if there is not enough free space.

        MicroPython ``os.statvfs`` returns a tuple where:
            index 0 = f_bsize (block size)
            index 4 = f_bavail (free blocks available to unprivileged user)
        """
        try:
            st = os.statvfs(path)
            bsize = st[0]
            bavail = st[4]
            free = bsize * bavail
        except (OSError, AttributeError, IndexError):
            # statvfs not available or wrong shape – cannot check, assume OK
            return
        if free < required_bytes:
            pretty = required_bytes // 1024
            raise RuntimeError(
                "Not enough free space (%d KB available, %d KB needed)"
                % (free // 1024, pretty)
            )

    @staticmethod
    def uninstall_app(app_fullname):
        try:
            import shutil
            shutil.rmtree(f"apps/{app_fullname}") # never in builtin/apps because those can't be uninstalled
        except Exception as e:
            logger.error("Removing app_folder apps/%s got error: %s", app_fullname, e)
        AppManager.refresh_apps()

    @staticmethod
    def install_mpk(temp_zip_path, dest_folder):
        import shutil
        import os
        from .streaming_unzip import StreamingUnzip

        try:
            # Step 1: Remove any existing (possibly partial) install or symlink
            try:
                st = os.stat(dest_folder)
                if st[0] & 0x4000:  # It's a real directory
                    shutil.rmtree(dest_folder)
                    if __debug__: logger.debug("Removed existing folder: %s", dest_folder)
                else:
                    os.remove(dest_folder)
                    if __debug__: logger.debug("Removed existing file: %s", dest_folder)
            except OSError:
                pass  # Doesn't exist, that's fine
            # Also remove if it's a symlink (broken or otherwise)
            try:
                os.remove(dest_folder)
                if __debug__: logger.debug("Removed symlink: %s", dest_folder)
            except OSError:
                pass  # Not a symlink or already removed

            # Step 2: Stream-extract the file in chunks
            if __debug__: logger.debug("Unzipping to: %s", dest_folder)

            dest_name = dest_folder.rstrip(os.sep).split(os.sep)[-1]
            extractor = StreamingUnzip(
                dest_folder,
                expected_app_name=dest_name,
                free_space_limit=lambda req: AppManager._check_free_space(".", req),
            )

            with open(temp_zip_path, "rb") as f:
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    extractor.feed(chunk)
            extractor.finish()

            if __debug__: logger.debug("Unzipped successfully")
            # Step 3: Clean up
            os.remove(temp_zip_path)
            if __debug__: logger.debug("Removed temporary .mpk file")
        except Exception as e:
            logger.error("install_mpk got exception, will attempt cleanup: %s", e)
            try:
                import shutil
                shutil.rmtree(dest_folder)
            except Exception:
                pass
            try:
                os.remove(temp_zip_path)
            except Exception as e:
                logger.error("install_mpk got os.remove exception: %s", e)
                import sys
                sys.print_exception(e)
            raise
        AppManager.refresh_apps()

    @staticmethod
    def compare_versions(ver1: str, ver2: str) -> bool:
        """Compare two version numbers (e.g., '1.2.3' vs '4.5.6').
        Returns True if ver1 is greater than ver2, False otherwise.
        Invalid or empty version numbers also result in False."""
        try:
            v1_parts = [int(x) for x in ver1.split('.')]
            v2_parts = [int(x) for x in ver2.split('.')]
        except ValueError as e:
            logger.error("Invalid input, got error: %s", e)
            return False
        for i in range(max(len(v1_parts), len(v2_parts))):
            v1 = v1_parts[i] if i < len(v1_parts) else 0
            v2 = v2_parts[i] if i < len(v2_parts) else 0
            if v1 > v2:
                return True
            if v1 < v2:
                return False
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
                if __debug__: logger.debug("is_installed_by_path: %s found, checking manifest...", dir_path)
                manifest = f"{dir_path}/META-INF/MANIFEST.JSON"
                if os.stat(manifest)[0] & 0x8000:
                    return True
        except OSError:
            if __debug__: logger.debug("is_installed_by_path got OSError for %s", dir_path)
            pass # Skip if directory or manifest doesn't exist
        return False

    @staticmethod
    def is_installed_by_name(app_fullname):
        if __debug__: logger.debug("Checking if app %s is installed...", app_fullname)
        return AppManager.is_installed_by_path(f"apps/{app_fullname}") or AppManager.is_installed_by_path(f"builtin/apps/{app_fullname}")

    @staticmethod
    def execute_script(script_source, classname, cwd=None, app_fullname=None):
        """Run an app entrypoint file by importing its module. Returns True if successful."""
        import utime # for timing read and compile
        import _thread
        import sys

        def _start_activity(main_activity, source_name):
            if main_activity:
                from mpos.activity_navigator import ActivityNavigator
                from .intent import Intent

                start_time = utime.ticks_ms()
                ActivityNavigator.startActivity(
                    Intent(activity_class=main_activity, app_fullname=app_fullname)
                )
                end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                if __debug__: logger.debug("ActivityNavigator.startActivity took %sms (%s)", end_time, source_name)
                return True
            logger.warning("could not find app's main_activity %s", classname)
            return False

        thread_id = _thread.get_ident()
        compile_name = script_source
        executed_name = compile_name
        if cwd and cwd != "/":
            cwd = cwd.rstrip("/")
        if __debug__: logger.debug("Thread %s: executing script with cwd: %s", thread_id, cwd)
        try:
            if __debug__: logger.debug("Thread %s: starting script", thread_id)
            path_before = sys.path[:]  # Make a copy, not a reference
            if cwd:
                if cwd in sys.path:
                    sys.path.remove(cwd)
                sys.path.insert(0, cwd)
            try:
                module_name = script_source.rsplit("/", 1)[-1]
                if "." in module_name:
                    module_name = module_name.rsplit(".", 1)[0]
                previous_module = sys.modules.get(module_name, None)
                had_previous_module = module_name in sys.modules
                try:
                    if had_previous_module:
                        del sys.modules[module_name]
                    start_time = utime.ticks_ms()
                    module = __import__(module_name)
                    import_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                    executed_name = getattr(module, "__file__", script_source)
                    if __debug__: logger.debug("importing module %s took %sms", module_name, import_time)
                    return _start_activity(getattr(module, classname, None), executed_name)
                except Exception as import_error:
                    logger.warning(
                        "failed importing app module %s from %s: %s", module_name, compile_name, import_error
                    )
                    sys.print_exception(import_error)
                    from mpos.ui.errordialog import show_app_error_dialog
                    show_app_error_dialog(
                        app_fullname, import_error, is_lifecycle=False
                    )
                    return False
                finally:
                    if had_previous_module:
                        sys.modules[module_name] = previous_module
                    elif module_name in sys.modules:
                        del sys.modules[module_name]
            except Exception as e:
                logger.error("Thread %s: exception during execution:", thread_id)
                sys.print_exception(e)
                from mpos.ui.errordialog import show_app_error_dialog
                show_app_error_dialog(
                    app_fullname, e, is_lifecycle=False
                )
                return False
            finally:
                # Always restore sys.path, even if we return early or raise an exception
                if __debug__: logger.debug("Thread %s: script %s finished, restoring sys.path from %s to %s", thread_id, executed_name, sys.path, path_before)
                sys.path = path_before
        except Exception as e:
            logger.error("Thread %s: error:", thread_id)
            import sys
            sys.print_exception(e)
            return False

    @staticmethod
    def start_app(fullname):
        """Start an app by fullname. Returns True if successful."""
        import utime
        start_time = utime.ticks_ms()
        app = AppManager.get(fullname)
        if not app:
            logger.warning("start_app can't find app %s", fullname)
            return
        if not app.installed_path:
            logger.warning("start_app can't start %s because no it doesn't have an installed_path", fullname)
            return
        entrypoint = "assets/main.py"
        classname = "Main"
        if not app.main_launcher_activity:
            logger.warning("app %s doesn't have a main_launcher_activity, defaulting to class %s in %s", fullname, classname, entrypoint)
        else:
            entrypoint = app.main_launcher_activity.get('entrypoint')
            classname = app.main_launcher_activity.get("classname")
        entrypoint_path = app.installed_path + "/" + entrypoint
        entrypoint_dir = app.installed_path
        if "/" in entrypoint:
            entrypoint_dir = entrypoint_path.rsplit("/", 1)[0]
        result = AppManager.execute_script(
            entrypoint_path,
            classname,
            entrypoint_dir,
            app_fullname=fullname,
        )
        # Launchers have the bar, other apps don't have it
        import mpos.ui
        if app.is_valid_launcher():
            mpos.ui.topmenu.open_bar()
        else:
            mpos.ui.topmenu.close_bar()
        end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
        if __debug__: logger.debug("start_app() took %sms", end_time)
        return result

    @classmethod
    def get_services_for_action(cls, action):
        """Returns list of (app_fullname, ServiceClass) for services matching action."""
        import sys
        results = []
        for app in cls.get_app_list():
            for svc in app.services:
                for f in svc.get("intent_filters", []):
                    if f.get("action") != action:
                        continue
                    entrypoint = svc.get("entrypoint")
                    classname = svc.get("classname")
                    if not entrypoint or not classname:
                        continue
                    entrypoint_path = app.installed_path + "/" + entrypoint
                    cwd = entrypoint_path.rsplit("/", 1)[0] if "/" in entrypoint else app.installed_path
                    path_before = sys.path[:]
                    try:
                        if cwd and cwd not in sys.path:
                            sys.path.insert(0, cwd)
                        module_name = entrypoint.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                        module = __import__(module_name)
                        service_cls = getattr(module, classname, None)
                        if service_cls:
                            results.append((app.fullname, service_cls))
                    except Exception as e:
                        logger.error("failed to import service %s from %s: %s", classname, app.fullname, e)
                    finally:
                        sys.path = path_before
        for fullname, service_cls in cls._service_registry.get(action, []):
            results.append((fullname, service_cls))
        return results

    @classmethod
    def start_boot_services(cls):
        import sys
        from .intent import Intent

        services = cls.get_services_for_action("boot_completed")
        if not services:
            if __debug__: logger.debug("no boot services found")
            return

        boot_intent = Intent(action="boot_completed")
        _service_instances = {}

        for fullname, service_cls in services:
            try:
                instance = service_cls()
                instance.appFullName = fullname
                key = (fullname, service_cls.__name__)
                _service_instances[key] = instance
                instance.onCreate()
                instance.onStart(boot_intent)
                if __debug__: logger.debug("started %s from %s", service_cls.__name__, fullname)
            except Exception as e:
                logger.error("failed to start %s from %s: %s", service_cls.__name__, fullname, e)
                sys.print_exception(e)

    @staticmethod
    def restart_launcher():
        """Restart the launcher by stopping all activities and starting the launcher app."""
        import mpos.ui
        if __debug__: logger.debug("restart_launcher")
        # Stop all apps
        mpos.ui.remove_and_stop_all_activities()
        # No need to stop the other launcher first, because it exits after building the screen
        return AppManager.start_app(AppManager.get_launcher().fullname)
