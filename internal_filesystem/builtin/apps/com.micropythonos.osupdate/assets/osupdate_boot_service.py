from mpos import Service, TaskManager

try:
    from osupdate_core import UpdateManager
except ImportError as e:
    UpdateManager = None
    print(f"OSUpdateService: osupdate_core unavailable: {e}")


class OSUpdateService(Service):

    def onStart(self, intent):
        if UpdateManager is None:
            return
        TaskManager.create_task(UpdateManager.get_instance().start())

    def onDestroy(self):
        if UpdateManager is None:
            return
        UpdateManager.get_instance().stop()
