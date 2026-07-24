import hashlib
import json
import logging

import ujson

from mpos import (
    AppManager,
    BuildInfo,
    ConnectivityManager,
    TaskManager,
    DownloadManager,
    NotificationManager,
    Notification,
    Intent,
    SharedPreferences,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Shared BadgeHub helpers (used by AppDetail and AppUpdateManager)
# ------------------------------------------------------------------


def _extract_main_executable(app_metadata):
    if not isinstance(app_metadata, dict):
        return None

    application = app_metadata.get("application")
    if isinstance(application, dict):
        executable = application.get("executable")
        if executable:
            return executable
    elif isinstance(application, list):
        for entry in application:
            if isinstance(entry, dict):
                executable = entry.get("executable")
                if executable:
                    return executable

    executable = app_metadata.get("executable")
    if executable:
        return executable

    return None


def _find_download_file(files, preferred_exts, app_version=None, main_executable=None):
    candidates = []
    for file in files:
        ext = file.get("ext")
        if ext is None:
            continue
        ext = str(ext).lower()
        if ext in preferred_exts:
            candidates.append(file)

    if not candidates:
        return None

    if main_executable:
        main_lower = str(main_executable).lower()
        for file in candidates:
            full_path = file.get("full_path", "")
            name = file.get("name", "")
            if str(full_path).lower() == main_lower or str(name).lower() == main_lower:
                return file

    if app_version is not None:
        version_marker = "_{}.mpk".format(app_version)
        version_name_marker = "_{}".format(app_version)
        for file in candidates:
            full_path = file.get("full_path", "")
            name = file.get("name", "")
            if str(full_path).lower().endswith(version_marker):
                return file
            if str(name).lower().endswith(version_name_marker):
                return file

    return candidates[0]


async def fetch_badgehub_project_details(details_url):
    try:
        response = await DownloadManager.download_url(details_url)
    except Exception as e:
        logger.warning("could not fetch details from %s: %s", details_url, e)
        return {}

    try:
        parsed = json.loads(response)
    except Exception as e:
        logger.warning("could not parse details JSON: %s", e)
        return {}

    result = {}
    try:
        version_obj = parsed.get("version")
        if not version_obj:
            return result
        app_metadata = version_obj.get("app_metadata") or {}
        files = version_obj.get("files")

        revision = version_obj.get("revision")
        if revision is not None:
            result["revision"] = revision

        result["version"] = app_metadata.get("version")
        result["publisher"] = app_metadata.get("author")
        result["long_description"] = app_metadata.get("long_description")

        if files:
            main_executable = _extract_main_executable(app_metadata)
            download_file = _find_download_file(
                files, [".mpk", ".zip"],
                app_version=result.get("version"),
                main_executable=main_executable,
            )
            if download_file:
                result["download_url"] = download_file.get("url")
                result["download_url_size"] = download_file.get("size_of_content")
    except Exception as e:
        logger.warning("could not parse app details: %s", e)

    return result


def _sha1_hex(data):
    from ubinascii import hexlify
    return hexlify(hashlib.sha1(data).digest()).decode()


def _get_device_mac_and_id():
    try:
        import machine
        unique_id = machine.unique_id()
        mac = ':'.join('%02x' % b for b in unique_id)
        return mac, _sha1_hex(mac.encode())
    except Exception:
        pass
    # ponytail: Linux fallback via /sys/class/net/; hostname fallback covers the rest
    try:
        import os
        for iface in os.listdir('/sys/class/net'):
            if iface == 'lo':
                continue
            with open('/sys/class/net/%s/address' % iface) as f:
                mac = f.read().strip().lower()
            if mac and mac != '00:00:00:00:00:00':
                return mac, _sha1_hex(mac.encode())
    except Exception as e:
        if __debug__: logger.debug("/sys/class/net/ fallback failed: %s", e)
    # ponytail: hostname as pseudo-id, stable and works everywhere
    try:
        import os
        hostname = os.getenv('HOSTNAME', '') or os.getenv('HOST', '')
        if hostname:
            return hostname, _sha1_hex(hostname.encode())
    except Exception as e:
        if __debug__: logger.debug("hostname fallback failed: %s", e)
    return None, None


async def report_badgehub_install(fullname, revision):
    mac, sha1_id = _get_device_mac_and_id()
    if not mac or not sha1_id:
        if __debug__: logger.debug("cannot report install: no device id available")
        return
    url = "https://badgehub.eu/api/v3/projects/%s/rev%s/report/install?mac=%s&id=%s" % (
        fullname, revision, mac, sha1_id,
    )
    try:
        await DownloadManager.post_url(url, data=b'', headers={'Accept': 'application/json'}, redact_url=True)
    except Exception as e:
        if __debug__: logger.debug("report install failed for %s: %s", fullname, e)


class AppUpdateState:
    IDLE = "idle"
    WAITING_WIFI = "waiting_wifi"
    CHECKING_UPDATES = "checking_updates"
    UPDATES_AVAILABLE = "updates_available"
    NO_UPDATES = "no_updates"
    ERROR = "error"


class AppUpdateManager:
    """Singleton that checks whether any installed store apps have newer versions available.

    Mirrors the design of osupdate_core.UpdateManager:
    - started at boot via a Service (appstore_boot_service.py)
    - the AppStore UI attaches/detaches a state-change callback
    - posts a system notification when updates are found
    """

    _instance = None

    BOOT_INITIAL_DELAY = 120       # seconds to wait after boot before first check
    BOOT_CHECK_INTERVAL = 60 * 60 * 24  # re-check every 24 h
    WIFI_CHECK_INTERVAL = 5

    NOTIFICATION_ID = "appstore.updates_available"
    ICON_PATH = "M:builtin/apps/com.micropythonos.appstore/icon_64x64.png"

    _PREF_KEY_BACKEND = "backend"

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if AppUpdateManager._instance is not None:
            raise RuntimeError("Use AppUpdateManager.get_instance()")

        self.current_state = AppUpdateState.IDLE
        self._running = False
        self._check_in_progress = False
        self._connectivity_manager = None
        self._state_callback = None
        self._suppress_notifications = False

        # Results of the last check
        self.updatable_apps = []   # list of App objects (from store) that are newer than installed

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def set_state_callback(self, callback):
        self._state_callback = callback

    def clear_state_callback(self):
        self._state_callback = None

    @property
    def suppress_notifications(self):
        return self._suppress_notifications

    @suppress_notifications.setter
    def suppress_notifications(self, value):
        self._suppress_notifications = bool(value)

    def _set_state(self, new_state):
        if __debug__: logger.debug("state %s -> %s", self.current_state, new_state)
        self.current_state = new_state
        if self._state_callback:
            try:
                self._state_callback(new_state)
            except Exception as e:
                logger.error("state callback error: %s", e)

    # ------------------------------------------------------------------
    # Background service loop
    # ------------------------------------------------------------------

    def start(self):
        self._running = True
        self._connectivity_manager = ConnectivityManager.get()
        self._connectivity_manager.register_callback(self._network_changed)
        TaskManager.create_task(self._run_loop())

    async def _run_loop(self):
        await TaskManager.sleep(self.BOOT_INITIAL_DELAY)

        while self._running:
            if self._check_in_progress:
                await TaskManager.sleep(1)
                continue

            if self._connectivity_manager.is_online():
                await self.check_for_updates()
            else:
                if __debug__: logger.debug("offline, skipping check")

            for _ in range(self.BOOT_CHECK_INTERVAL):
                if not self._running:
                    return
                await TaskManager.sleep(1)

    def stop(self):
        if __debug__: logger.debug("stopping")
        self._running = False
        if self._connectivity_manager:
            self._connectivity_manager.unregister_callback(self._network_changed)

    def check_for_updates_now(self, index_url=None):
        """Kick off a one-off update check if none is already in progress."""
        if self._check_in_progress:
            return
        TaskManager.create_task(self.check_for_updates(index_url))

    def _network_changed(self, online):
        if __debug__: logger.debug("network %s", "ONLINE" if online else "OFFLINE")
        if online:
            if self.current_state in (
                AppUpdateState.IDLE,
                AppUpdateState.WAITING_WIFI,
                AppUpdateState.ERROR,
            ):
                TaskManager.create_task(self.check_for_updates())
        else:
            if self.current_state in (AppUpdateState.IDLE, AppUpdateState.CHECKING_UPDATES):
                self._set_state(AppUpdateState.WAITING_WIFI)

    # ------------------------------------------------------------------
    # Core update check
    # ------------------------------------------------------------------

    def _get_index_url_and_type(self):
        prefs = SharedPreferences("com.micropythonos.appstore")
        pref_string = prefs.get_string(self._PREF_KEY_BACKEND, "badgehub,https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_%s,https://badgehub.eu/api/v3/projects" % BuildInfo.version.api_level)
        parts = pref_string.split(",")
        backend_type = parts[0]
        list_url = parts[1]
        return list_url, backend_type

    async def check_for_updates(self, index_url=None):
        """Download the app index and compare versions against installed apps.

        ``index_url`` defaults to the production index.  The AppStore UI
        may pass its own backend URL when the user has changed the backend setting.
        """
        if self._check_in_progress:
            return
        self._check_in_progress = True
        try:
            self._set_state(AppUpdateState.CHECKING_UPDATES)

            backend_type = "github"
            if index_url is None:
                index_url, backend_type = self._get_index_url_and_type()

            try:
                response = await DownloadManager.download_url(index_url)
            except Exception as e:
                logger.error("download error: %s", e)
                if DownloadManager.is_network_error(e):
                    self._set_state(AppUpdateState.WAITING_WIFI)
                else:
                    self._set_state(AppUpdateState.ERROR)
                return

            try:
                apps_json = ujson.loads(response)
            except Exception as e:
                logger.error("JSON parse error: %s", e)
                self._set_state(AppUpdateState.ERROR)
                return

            updatable = []
            for app_data in apps_json:
                try:
                    if backend_type == "badgehub":
                        fullname = app_data.get("slug")
                        remote_version = app_data.get("version")
                        if not fullname or not remote_version:
                            continue
                        if AppManager.is_update_available(fullname, remote_version):
                            updatable.append({
                                "fullname": fullname,
                                "version": remote_version,
                                "name": app_data.get("name", fullname),
                                "download_url": None,
                            })
                    else:
                        fullname = app_data.get("fullname")
                        remote_version = app_data.get("version")
                        if not fullname or not remote_version:
                            continue
                        if AppManager.is_update_available(fullname, remote_version):
                            updatable.append(app_data)
                except Exception as e:
                    logger.error("error checking %s: %s", app_data, e)

            self.updatable_apps = updatable

            if updatable:
                self._set_state(AppUpdateState.UPDATES_AVAILABLE)
                self._notify_updates_available()
            else:
                self._set_state(AppUpdateState.NO_UPDATES)
                self._clear_notification()

        finally:
            self._check_in_progress = False

    # ------------------------------------------------------------------
    # Notification helpers
    # ------------------------------------------------------------------

    def _notify_updates_available(self):
        if self._suppress_notifications:
            if __debug__: logger.debug("suppressing notification (AppStore in foreground)")
            return
        n = len(self.updatable_apps)
        text = f"{n} app{'s' if n != 1 else ''} can be updated"
        NotificationManager.notify(
            Notification(
                notification_id=self.NOTIFICATION_ID,
                icon=self.ICON_PATH,
                title="App updates available",
                text=text,
                priority=Notification.PRIORITY_DEFAULT,
                intent=Intent(app_fullname="com.micropythonos.appstore"),
                auto_cancel=True,
                app_fullname="com.micropythonos.appstore",
            )
        )

    def _clear_notification(self):
        NotificationManager.cancel(self.NOTIFICATION_ID)
