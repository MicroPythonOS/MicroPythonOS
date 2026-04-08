# connectivity.py — Universal ConnectivityManager for MicroPythonOS
# Works on ESP32, ESP8266, Unix/Desktop, and anything else

import sys
import time

try:
    import network
    HAS_NETWORK_MODULE = True
except ImportError:
    HAS_NETWORK_MODULE = False

class ConnectivityManager:
    _instance = None

    def __init__(self):
        #print("connectivity_manager.py init")
        if ConnectivityManager._instance:
            return
        ConnectivityManager._instance = self

        self.can_check_network = HAS_NETWORK_MODULE

        if self.can_check_network:
            self.wlan = network.WLAN(network.STA_IF)
        else:
            self.wlan = None

        self.is_connected = False      # Local network (Wi-Fi/AP) connected
        self._is_online = False         # Real internet reachability
        self.callbacks = []
        self._reconnect_in_progress = False
        self._offline_checks = 0       # Count consecutive offline checks
        self._RECONNECT_INTERVAL = 38  # Attempt reconnect every 38 checks (~5 minutes at 8s interval)

        if not self.can_check_network:
            self.is_connected = True # If there's no way to check, then assume we're always "connected" and online

        # Start periodic validation timer (only on real embedded targets)
        from machine import Timer # Import Timer lazily to allow test mocks to be set up first
        self._check_timer = Timer(1) # 0 is already taken by task_handler.py
        self._check_timer.init(period=8000, mode=Timer.PERIODIC, callback=self._periodic_check_connected)
        
        self._periodic_check_connected(notify=False)
        #print("init done")

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        #print("returning...")
        return cls._instance

    def register_callback(self, callback):
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def unregister_callback(self, callback):
        self.callbacks = [cb for cb in self.callbacks if cb != callback]

    def _notify(self, now_online):
        for cb in self.callbacks:
            try:
                cb(now_online)
            except Exception as e:
                print("[Connectivity] Callback error:", e)

    def _periodic_check_connected(self, notify=True):
        #print("_periodic_check_connected")
        was_online = self._is_online
        if not self.can_check_network:
            self._is_online = True
        else:
            if self.wlan.isconnected():
                self._is_online = True
                self._offline_checks = 0
            else:
                self._is_online = False
                self._offline_checks += 1
                # Periodically attempt to reconnect WiFi
                if self._offline_checks % self._RECONNECT_INTERVAL == 0 and not self._reconnect_in_progress:
                    self._attempt_reconnect()

        if self._is_online != was_online:
            status = "ONLINE" if self._is_online else "OFFLINE"
            print(f"[Connectivity] Internet => {status}")
            if notify:
                self._notify(self._is_online)

    def _attempt_reconnect(self):
        """Attempt to reconnect WiFi in a background thread."""
        try:
            from .wifi_service import WifiService
            if WifiService.wifi_busy:
                return
            self._reconnect_in_progress = True
            print(f"[Connectivity] WiFi offline for ~{self._offline_checks * 8}s, attempting reconnect...")
            import _thread
            def reconnect_thread():
                try:
                    WifiService.auto_connect()
                finally:
                    self._reconnect_in_progress = False
            _thread.start_new_thread(reconnect_thread, ())
        except Exception as e:
            print(f"[Connectivity] Reconnect failed: {e}")
            self._reconnect_in_progress = False

    # === Public Android-like API ===
    def is_online(self):
        return self._is_online

    def is_wifi_connected(self):
        return self.is_connected

    def wait_until_online(self, timeout=60):
         if not self.can_check_network:
             return True
         start = time.time()
         while time.time() - start < timeout:
             if self.is_online:
                 return True
             time.sleep(1)
         return False


# ============================================================================
# Class method delegation (at module level)
# ============================================================================

_original_methods = {}
_methods_to_delegate = [
    'is_online', 'is_wifi_connected', 'wait_until_online',
    'register_callback', 'unregister_callback'
]

for method_name in _methods_to_delegate:
    _original_methods[method_name] = getattr(ConnectivityManager, method_name)

def _make_class_method(method_name):
    """Create a class method that delegates to the singleton instance."""
    original_method = _original_methods[method_name]
    
    @classmethod
    def class_method(cls, *args, **kwargs):
        instance = cls.get()
        return original_method(instance, *args, **kwargs)
    
    return class_method

for method_name in _methods_to_delegate:
    setattr(ConnectivityManager, method_name, _make_class_method(method_name))
