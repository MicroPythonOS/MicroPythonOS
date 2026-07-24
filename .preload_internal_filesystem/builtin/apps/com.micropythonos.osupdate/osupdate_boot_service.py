import logging

from mpos import Service

logger = logging.getLogger(__name__)

try:
    from osupdate_core import UpdateManager
except ImportError as e:
    UpdateManager = None
    logger.error("osupdate_core unavailable: %s", e)


class OSUpdateService(Service):

    def onStart(self, intent):
        if UpdateManager is None:
            return
        UpdateManager.get_instance().start()

    def onDestroy(self):
        if UpdateManager is None:
            return
        UpdateManager.get_instance().stop()
