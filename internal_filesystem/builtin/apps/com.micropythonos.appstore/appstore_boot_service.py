import logging

from mpos import Service

logger = logging.getLogger(__name__)

try:
    from appstore_core import AppUpdateManager
except ImportError as e:
    AppUpdateManager = None
    logger.error("appstore_core unavailable: %s", e)


class AppStoreService(Service):

    def onStart(self, intent):
        if AppUpdateManager is None:
            return
        AppUpdateManager.get_instance().start()

    def onDestroy(self):
        if AppUpdateManager is None:
            return
        AppUpdateManager.get_instance().stop()
