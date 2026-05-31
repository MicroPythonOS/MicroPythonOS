from .service import Service
from ..content.app_manager import AppManager


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


AppManager.register_service("boot_completed", WifiBootService, fullname="com.micropythonos.system")
AppManager.register_service("boot_completed", WebServerBootService, fullname="com.micropythonos.system")
