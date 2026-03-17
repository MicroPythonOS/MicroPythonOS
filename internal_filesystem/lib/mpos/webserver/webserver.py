"""WebServer control for MicroPythonOS."""

from ..config import SharedPreferences
from .webrepl_http import accept_handler


class WebServer:
    PREFS_NAMESPACE = "com.micropythonos.webserver"
    DEFAULTS = {
        "autostart": "False",
        "port": "7890",
        "password": "MPOSweb26",
    }

    _started = False
    _port = None
    _password = None
    _autostart = None
    _last_error = None

    @classmethod
    def _prefs(cls):
        return SharedPreferences(cls.PREFS_NAMESPACE, defaults=cls.DEFAULTS)

    @classmethod
    def _parse_bool(cls, value):
        return str(value).lower() in ("true", "1", "yes", "on")

    @classmethod
    def _parse_port(cls, value):
        try:
            return int(value)
        except Exception:
            return int(cls.DEFAULTS["port"])

    @classmethod
    def _sanitize_password(cls, value):
        if not value:
            value = cls.DEFAULTS["password"]
        if len(value) > 9:
            value = value[:9]
        return value

    @classmethod
    def load_settings(cls):
        prefs = cls._prefs()
        cls._autostart = cls._parse_bool(prefs.get_string("autostart", cls.DEFAULTS["autostart"]))
        cls._port = cls._parse_port(prefs.get_string("port", cls.DEFAULTS["port"]))
        cls._password = cls._sanitize_password(prefs.get_string("password", cls.DEFAULTS["password"]))

    @classmethod
    def status(cls):
        cls.load_settings()
        return {
            "state": "started" if cls._started else "stopped",
            "started": cls._started,
            "port": cls._port,
            "password": cls._password,
            "autostart": cls._autostart,
            "last_error": cls._last_error,
        }

    @classmethod
    def is_started(cls):
        return cls._started

    @classmethod
    def start(cls):
        cls.load_settings()
        try:
            from . import webrepl

            webrepl.start(port=cls._port, password=cls._password, accept_handler=accept_handler)
            cls._started = True
            cls._last_error = None
            print(f"WebServer started on port {cls._port}")
            return True
        except Exception as exc:
            cls._last_error = exc
            cls._started = False
            print(f"WebServer start failed: {exc}")
            return False

    @classmethod
    def stop(cls):
        try:
            from . import webrepl

            if hasattr(webrepl, "stop"):
                webrepl.stop()
            cls._started = False
            cls._last_error = None
            print("WebServer stopped")
            return True
        except Exception as exc:
            cls._last_error = exc
            print(f"WebServer stop failed: {exc}")
            return False

    @classmethod
    def apply_settings(cls, restart_if_running=True):
        was_running = cls._started
        cls.load_settings()
        if was_running and restart_if_running:
            cls.stop()
            cls.start()
        return cls.status()

    @classmethod
    def auto_start(cls):
        cls.load_settings()
        if cls._autostart:
            return cls.start()
        print("WebServer autostart disabled")
        return False
