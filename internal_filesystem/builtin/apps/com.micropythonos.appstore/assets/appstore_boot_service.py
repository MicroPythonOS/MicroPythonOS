from mpos import Service

try:
    from appstore_core import AppUpdateManager
except ImportError as e:
    AppUpdateManager = None
    print(f"AppStoreService: appstore_core unavailable: {e}")


class AppStoreService(Service):

    def onStart(self, intent):
        if AppUpdateManager is None:
            return
        AppUpdateManager.get_instance().start()

    def onDestroy(self):
        if AppUpdateManager is None:
            return
        AppUpdateManager.get_instance().stop()
