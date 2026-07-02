import logging
from .service import Service
from ..content.app_manager import AppManager

logger = logging.getLogger(__name__)


class WifiBootService(Service):

    def onStart(self, intent):
        import _thread
        from ..net.wifi_service import WifiService
        from ..task_manager import TaskManager
        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(WifiService.auto_connect, ())


class WebServerBootService(Service):

    def onStart(self, intent):
        from ..webserver.webserver import WebServer
        WebServer.auto_start()


class AIOReplService(Service):

    def onStart(self, intent):
        import aiorepl
        import lvgl as lv
        import mpos
        from ..task_manager import TaskManager

        async def asyncio_repl():
            logger.warning("Starting very limited asyncio REPL task. To stop all asyncio tasks and go to real REPL, do: mpos.TaskManager.stop()")
            await aiorepl.task(g={"lv": lv, "mpos": mpos}, prompt=">>> ")
        TaskManager.create_task(asyncio_repl())


AppManager.register_service("boot_completed", WifiBootService, fullname="com.micropythonos.system")
AppManager.register_service("boot_completed", WebServerBootService, fullname="com.micropythonos.system")
AppManager.register_service("boot_completed", AIOReplService, fullname="com.micropythonos.system")
