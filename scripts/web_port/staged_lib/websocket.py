# Stub for the native `websocket` module (unavailable in the web build).


class websocket:
    def __init__(self, *args, **kwargs):
        raise OSError("websocket not available in the web build")
