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

class HandlerInfo:
    """Lightweight descriptor returned by resolve_activity().

    Attributes:
        activity_class: The Activity subclass that can handle the intent.
        app_fullname: The fullname of the installed app that owns the handler,
            or None for framework-level handlers (e.g. ViewActivity).
    """

    def __init__(self, activity_class, app_fullname=None):
        self.activity_class = activity_class
        self.app_fullname = app_fullname


class AppManager:

    _registry = {}          # action → [ActivityClass, ...]
    _service_registry = {}  # action → [(fullname_or_None, ServiceClass), ...]

    # File-type intent handlers discovered from app manifests.
    # action → [{app_fullname, entrypoint, classname, mime_type, path_pattern}, ...]
    _file_handler_specs = {}

    # Lazily imported handler classes: (app_fullname, entrypoint, classname) → class
    _handler_class_cache = {}

    # Map from handler class back to its owning app fullname (populated lazily).
    _handler_app_fullname = {}

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
    def _register_file_handler_spec(cls, action, app_fullname, entrypoint, classname,
                                     mime_type=None, path_pattern=None):
        """Store a manifest-declared file-type handler for lazy resolution."""
        if action not in cls._file_handler_specs:
            cls._file_handler_specs[action] = []
        cls._file_handler_specs[action].append({
            "app_fullname": app_fullname,
            "entrypoint": entrypoint,
            "classname": classname,
            "mime_type": mime_type,
            "path_pattern": path_pattern,
        })

    @staticmethod
    def _is_valid_identifier(s):
        if not s:
            return False

        def _is_alpha(ch):
            o = ord(ch)
            return (o >= 97 and o <= 122) or (o >= 65 and o <= 90)

        def _is_alnum(ch):
            o = ord(ch)
            return _is_alpha(ch) or (o >= 48 and o <= 57)

        first = s[0]
        if not (_is_alpha(first) or first == "_"):
            return False
        for c in s[1:]:
            if not (_is_alnum(c) or c == "_"):
                return False
        return True

    @staticmethod
    def _has_init_module(path):
        import os
        return os.path.isfile(path + "/__init__.py") or os.path.isfile(path + "/__init__.mpy")

    @staticmethod
    def _drop_py_extension(s):
        if s.endswith(".py"):
            return s[:-3]
        if s.endswith(".mpy"):
            return s[:-4]
        return s

    @classmethod
    def _package_info(cls, app, entrypoint):
        """Return (parent_dir, dotted_module_name) if app should load as a package.

        Package loading is opt-in: the app root must contain __init__.py or __init__.mpy
        and every directory on the path to the entrypoint must also contain one.
        This lets old-style apps keep loading as flat modules while new apps can
        use packages to avoid namespace collisions between apps.
        """
        root = app.installed_path
        if not cls._has_init_module(root):
            return None
        parts = entrypoint.split("/")
        for i in range(len(parts) - 1):
            sub = root + "/" + "/".join(parts[:i + 1])
            if not cls._has_init_module(sub):
                return None
        for part in app.fullname.split("."):
            if not cls._is_valid_identifier(part):
                return None
        module_name = app.fullname + "." + cls._drop_py_extension(".".join(parts))
        parent = "/".join(root.split("/")[:-1])
        return parent, module_name

    @staticmethod
    def _del_module_tree(module_name):
        """Remove a module and any cached submodules from sys.modules."""
        import sys
        keys = [k for k in sys.modules if k == module_name or k.startswith(module_name + ".")]
        for k in keys:
            del sys.modules[k]

    @classmethod
    def _import_handler_class(cls, spec):
        """Import the activity class for a file-handler spec, caching the result."""
        key = (spec["app_fullname"], spec["entrypoint"], spec["classname"])
        cached = cls._handler_class_cache.get(key)
        if cached is not None:
            cls._handler_app_fullname[cached] = spec["app_fullname"]
            return cached

        import sys
        app = cls.get(spec["app_fullname"])
        if app is None or not app.installed_path:
            return None

        path_before = sys.path[:]
        pkg = cls._package_info(app, spec["entrypoint"])
        if pkg:
            parent, module_name = pkg
            try:
                if parent and parent not in sys.path:
                    sys.path.insert(0, parent)
                cls._del_module_tree(module_name)
                module = __import__(module_name, None, None, [spec["classname"]])
                activity_cls = getattr(module, spec["classname"], None)
                if activity_cls is not None:
                    cls._handler_class_cache[key] = activity_cls
                    cls._handler_app_fullname[activity_cls] = spec["app_fullname"]
                return activity_cls
            except Exception as e:
                logger.error("failed to import file handler %s from %s: %s",
                             spec["classname"], spec["app_fullname"], e)
                return None
            finally:
                sys.path = path_before

        entrypoint_path = app.installed_path + "/" + spec["entrypoint"]
        cwd = app.installed_path
        if "/" in spec["entrypoint"]:
            cwd = entrypoint_path.rsplit("/", 1)[0]

        module_name = spec["entrypoint"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        previous_module = sys.modules.get(module_name, None)
        had_previous_module = module_name in sys.modules
        try:
            if cwd and cwd not in sys.path:
                sys.path.insert(0, cwd)
            if had_previous_module:
                del sys.modules[module_name]
            module = __import__(module_name)
            activity_cls = getattr(module, spec["classname"], None)
            if activity_cls is not None:
                cls._handler_class_cache[key] = activity_cls
                cls._handler_app_fullname[activity_cls] = spec["app_fullname"]
            return activity_cls
        except Exception as e:
            logger.error("failed to import file handler %s from %s: %s",
                         spec["classname"], spec["app_fullname"], e)
            return None
        finally:
            sys.path = path_before
            if had_previous_module:
                sys.modules[module_name] = previous_module
            elif module_name in sys.modules:
                del sys.modules[module_name]

    @staticmethod
    def _path_matches(path_pattern, path):
        """Check whether a file path matches a pathPattern like *.wav or [".png", ".jpg"]."""
        if not path_pattern:
            return True
        if isinstance(path_pattern, str):
            patterns = [path_pattern]
        else:
            patterns = path_pattern
        lower_path = path.lower()
        for pat in patterns:
            pat = pat.strip().lower()
            if pat.startswith("*"):
                pat = pat[1:]
            if lower_path.endswith(pat):
                return True
        return False

    @classmethod
    def _file_specific_handlers(cls, action, data):
        """Return HandlerInfo objects for manifest handlers that match the file path."""
        results = []
        for spec in cls._file_handler_specs.get(action, []):
            if cls._path_matches(spec.get("path_pattern"), data):
                activity_cls = cls._import_handler_class(spec)
                if activity_cls is not None:
                    results.append(HandlerInfo(activity_cls, spec["app_fullname"]))
        return results

    @classmethod
    def resolve_activity(cls, intent):
        """Return a list of HandlerInfo objects that can handle the intent."""
        generic = [
            HandlerInfo(activity_cls)
            for activity_cls in cls._registry.get(intent.action, [])
        ]

        if intent.data and isinstance(intent.data, str):
            specific = cls._file_specific_handlers(intent.action, intent.data)
            if specific:
                return specific
            # Fall back to generic handlers if no specific file handler matched.
            return generic

        return generic

    @classmethod
    def query_intent_activities(cls, intent):
        """Same as resolve_activity – more Android-like name."""
        return cls.resolve_activity(intent)

    @classmethod
    def get_handler_display_name(cls, activity_class):
        """Return a human-readable name for a resolved handler class."""
        fullname = cls._handler_app_fullname.get(activity_class)
        if fullname:
            app = cls.get(fullname)
            if app:
                return app.name
        return activity_class.__name__

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
        cls._file_handler_specs = {}
        cls._handler_class_cache = {}
        cls._handler_app_fullname = {}

    @classmethod
    def refresh_apps(cls):
        if __debug__: logger.debug("Finding apps...")

        cls.clear()                     # <-- this guarantees both containers are empty
        seen = set()                     # avoid processing the same fullname twice
        apps_dir         = "apps"
        apps_dir_builtin = "builtin/" + apps_dir
        # relative paths are here for local-file desktop runs and also ESP32 builds
        # "/" + apps_dir_builtin is here for frozen-only desktop runs (no local files)
        # "/" + apps_dir_builtin is not here because there's no use case for it currently
        for base in (apps_dir, apps_dir_builtin, "/" + apps_dir_builtin):
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

                    # ---- register manifest file-type handlers (lazy) -------
                    for act in app.activities:
                        entrypoint = act.get("entrypoint")
                        classname = act.get("classname")
                        if not entrypoint or not classname:
                            continue
                        for f in act.get("intent_filters", []):
                            action = f.get("action")
                            if not action:
                                continue
                            mime_type = f.get("mimeType")
                            path_pattern = f.get("pathPattern")
                            if mime_type or path_pattern:
                                cls._register_file_handler_spec(
                                    action, app.fullname, entrypoint, classname,
                                    mime_type=mime_type, path_pattern=path_pattern,
                                )

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
                for manifest in (f"{dir_path}/MANIFEST.JSON", f"{dir_path}/META-INF/MANIFEST.JSON"):
                    try:
                        if os.stat(manifest)[0] & 0x8000:
                            return True
                    except OSError:
                        continue
        except OSError:
            if __debug__: logger.debug("is_installed_by_path got OSError for %s", dir_path)
            pass # Skip if directory or manifest doesn't exist
        return False

    @staticmethod
    def is_installed_by_name(app_fullname):
        if __debug__: logger.debug("Checking if app %s is installed...", app_fullname)
        return AppManager.is_installed_by_path(f"apps/{app_fullname}") or AppManager.is_installed_by_path(f"builtin/apps/{app_fullname}")

    @staticmethod
    def execute_script(script_source, classname, cwd=None, app_fullname=None, intent=None, result_callback=None):
        """Run an app entrypoint file by importing its module. Returns True if successful."""
        import utime # for timing read and compile
        import _thread
        import sys

        def _start_activity(main_activity, source_name):
            if main_activity:
                from mpos.activity_navigator import ActivityNavigator
                from .intent import Intent

                if intent is None:
                    launch_intent = Intent(activity_class=main_activity, app_fullname=app_fullname)
                else:
                    launch_intent = intent
                    launch_intent.activity_class = main_activity
                    launch_intent.app_fullname = app_fullname

                start_time = utime.ticks_ms()
                ActivityNavigator._launch_activity(launch_intent, result_callback=result_callback)
                end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
                if __debug__: logger.debug("_launch_activity took %sms (%s)", end_time, source_name)
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
            path_to_add = cwd
            is_package = False
            app = None
            if app_fullname:
                app = AppManager.get(app_fullname)
            if app and app.installed_path and script_source.startswith(app.installed_path + "/"):
                entrypoint = script_source[len(app.installed_path) + 1:]
                pkg = AppManager._package_info(app, entrypoint)
                if pkg:
                    parent, module_name = pkg
                    path_to_add = parent
                    is_package = True

            if path_to_add:
                if path_to_add in sys.path:
                    sys.path.remove(path_to_add)
                sys.path.insert(0, path_to_add)
            try:
                if is_package:
                    try:
                        AppManager._del_module_tree(module_name)
                        start_time = utime.ticks_ms()
                        module = __import__(module_name, None, None, [classname])
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
                else:
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
    def start_app(fullname, intent=None, result_callback=None):
        """Start an app by fullname. Returns True if successful.

        If ``intent`` is provided, the app's main launcher activity receives it
        (typically via Activity.getIntent()). This is how "Open With" passes a
        file path to the target app.

        If ``result_callback`` is provided, it is attached to the launched
        activity so the app can return a result via Activity.finish().
        """
        import utime
        start_time = utime.ticks_ms()
        app = AppManager.get(fullname)
        if not app:
            logger.warning("start_app can't find app %s", fullname)
            return False
        if not app.installed_path:
            logger.warning("start_app can't start %s because no it doesn't have an installed_path", fullname)
            return False
        if not app.main_launcher_activity:
            logger.error("app %s has no main_launcher_activity in manifest; cannot start", fullname)
            return False
        entrypoint = app.main_launcher_activity.get('entrypoint')
        classname = app.main_launcher_activity.get("classname")
        if not entrypoint or not classname:
            logger.error("app %s main_launcher_activity is missing entrypoint or classname", fullname)
            return False
        entrypoint_path = app.installed_path + "/" + entrypoint
        entrypoint_dir = app.installed_path
        if "/" in entrypoint:
            entrypoint_dir = entrypoint_path.rsplit("/", 1)[0]
        result = AppManager.execute_script(
            entrypoint_path,
            classname,
            entrypoint_dir,
            app_fullname=fullname,
            intent=intent,
            result_callback=result_callback,
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
                    path_before = sys.path[:]
                    try:
                        pkg = cls._package_info(app, entrypoint)
                        if pkg:
                            parent, module_name = pkg
                            if parent and parent not in sys.path:
                                sys.path.insert(0, parent)
                            cls._del_module_tree(module_name)
                            module = __import__(module_name, None, None, [classname])
                        else:
                            entrypoint_path = app.installed_path + "/" + entrypoint
                            cwd = entrypoint_path.rsplit("/", 1)[0] if "/" in entrypoint else app.installed_path
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
