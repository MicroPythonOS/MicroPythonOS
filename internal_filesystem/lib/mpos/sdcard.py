import os
import machine
import vfs

class SDCardManager:
    def __init__(self, spi_bus, cs_pin):
        self._sdcard = None
        try:
            self._sdcard = machine.SDCard(spi_bus=spi_bus, cs=cs_pin)
            self._sdcard.info()
            print("SD card initialized")
        except Exception as e:
            print(f"ERROR: Failed to initialize SD card: {e}")

    def mount(self, mount_point):
        if not self._sdcard:
            return False
        try:
            os.mount(self._sdcard, mount_point)
            print(f"Mounted at {mount_point}")
            return True
        except OSError as e:
            print(f"Mount failed: {e}")
            return False

    def format_and_mount(self, mount_point):
        if not self._sdcard:
            return False
        print("Formatting SD card...")
        try:
            os.umount(mount_point)
        except:
            pass
        try:
            vfs.VfsFat.mkfs(self._sdcard)
            print("Formatted")
            return self.mount(mount_point)
        except OSError as e:
            print(f"Format failed: {e}")
            return False

    def is_mounted(self, mount_point):
        try:
            return mount_point in os.listdir('/') and os.path.ismount(mount_point)
        except:
            return False

    def list(self, mount_point):
        try:
            return os.listdir(mount_point)
        except:
            return []

# --- Global instance (singleton) ---
_manager = None

def init(spi_bus, cs_pin):
    """Initialize the global SD card manager."""
    global _manager
    if _manager is None:
        _manager = SDCardManager(spi_bus, cs_pin)
    return _manager

def get():
    """Get the global SD card manager instance."""
    return _manager

# Optional: convenience functions
def mount(mount_point):
    mgr = get()
    return mgr and mgr.mount(mount_point)

def mount_with_format(mount_point):
    mgr = get()
    if mgr and not mgr.mount(mount_point):
        return mgr.format_and_mount(mount_point)
    return mgr and mgr.is_mounted(mount_point)
