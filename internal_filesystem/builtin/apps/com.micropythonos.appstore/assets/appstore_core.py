import ujson

from mpos import (
    AppManager,
    ConnectivityManager,
    TaskManager,
    DownloadManager,
    NotificationManager,
    Notification,
    Intent,
)


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

    BOOT_INITIAL_DELAY = 90       # seconds to wait after boot before first check
    BOOT_CHECK_INTERVAL = 60 * 60 * 24  # re-check every 24 h
    WIFI_CHECK_INTERVAL = 5

    NOTIFICATION_ID = "appstore.updates_available"
    ICON_PATH = "M:builtin/apps/com.micropythonos.appstore/res/mipmap-mdpi/icon_64x64.png"

    _GITHUB_PROD_BASE_URL = "https://apps.micropythonos.com"
    _GITHUB_LIST = "/app_index.json"

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
        print(f"AppUpdateManager: {self.current_state} -> {new_state}")
        self.current_state = new_state
        if self._state_callback:
            try:
                self._state_callback(new_state)
            except Exception as e:
                print(f"AppUpdateManager: state callback error: {e}")

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
                print("AppUpdateManager: offline, skipping check")

            for _ in range(self.BOOT_CHECK_INTERVAL):
                if not self._running:
                    return
                await TaskManager.sleep(1)

    def stop(self):
        print("AppUpdateManager: stopping")
        self._running = False
        if self._connectivity_manager:
            self._connectivity_manager.unregister_callback(self._network_changed)

    def check_for_updates_now(self, index_url=None):
        """Kick off a one-off update check if none is already in progress."""
        if self._check_in_progress:
            return
        TaskManager.create_task(self.check_for_updates(index_url))

    def _network_changed(self, online):
        print(f"AppUpdateManager: network {'ONLINE' if online else 'OFFLINE'}")
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

    async def check_for_updates(self, index_url=None):
        """Download the GitHub app index and compare versions against installed apps.

        ``index_url`` defaults to the GitHub production index.  The AppStore UI
        may pass its own backend URL when the user has changed the backend setting.
        """
        if self._check_in_progress:
            return
        self._check_in_progress = True
        try:
            self._set_state(AppUpdateState.CHECKING_UPDATES)

            if index_url is None:
                index_url = self._GITHUB_PROD_BASE_URL + self._GITHUB_LIST

            try:
                response = await DownloadManager.download_url(index_url)
            except Exception as e:
                print(f"AppUpdateManager: download error: {e}")
                if DownloadManager.is_network_error(e):
                    self._set_state(AppUpdateState.WAITING_WIFI)
                else:
                    self._set_state(AppUpdateState.ERROR)
                return

            try:
                apps_json = ujson.loads(response)
            except Exception as e:
                print(f"AppUpdateManager: JSON parse error: {e}")
                self._set_state(AppUpdateState.ERROR)
                return

            updatable = []
            for app_data in apps_json:
                try:
                    fullname = app_data.get("fullname")
                    remote_version = app_data.get("version")
                    if not fullname or not remote_version:
                        continue
                    if AppManager.is_update_available(fullname, remote_version):
                        updatable.append(app_data)
                except Exception as e:
                    print(f"AppUpdateManager: error checking {app_data}: {e}")

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
            print("AppUpdateManager: suppressing notification because AppStore is in foreground")
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
