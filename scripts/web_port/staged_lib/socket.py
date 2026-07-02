# Minimal socket stub for the WebAssembly/Emscripten build.
#
# The browser sandbox has no access to raw TCP/UDP sockets, so MicroPythonOS'
# network server features (WebREPL, web server) are unavailable on web. This
# stub lets `import socket` succeed at boot; constructing or using a socket
# raises OSError so callers can detect and skip networking gracefully.

AF_INET = 2
AF_INET6 = 10
SOCK_STREAM = 1
SOCK_DGRAM = 2
SOL_SOCKET = 1
SO_REUSEADDR = 2
IPPROTO_TCP = 6
IPPROTO_UDP = 17


class error(OSError):
    pass


def getaddrinfo(host, port, *args, **kwargs):
    raise OSError("socket not available in the web build")


class socket:
    def __init__(self, *args, **kwargs):
        raise OSError("socket not available in the web build")
