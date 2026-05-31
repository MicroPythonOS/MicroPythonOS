from mpos import Service, ConnectivityManager, TaskManager


class OSUpdateService(Service):

    def __init__(self):
        super().__init__()
        self._running = False

    def onStart(self, intent):
        self._running = True
        TaskManager.create_task(self._boot_loop())

    def onDestroy(self):
        self._running = False

    async def _boot_loop(self):
        cm = ConnectivityManager.get()
        while self._running:
            await TaskManager.sleep(30)
            if cm.is_online():
                print("OSUpdateService: network connected")
            else:
                print("OSUpdateService: network not connected")
