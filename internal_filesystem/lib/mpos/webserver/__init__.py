"""Web server helpers for MicroPythonOS."""

from .webrepl_http import accept_handler
from .webserver import WebServer

__all__ = ["accept_handler", "WebServer"]
