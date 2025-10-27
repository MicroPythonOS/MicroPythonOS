import os
import machine
import vfs

class SDCardManager:
    def __init__(self, spi_bus, cs_pin):
        self._sdcard = None
        try:
            self._sdcard = machine.SDCard(spi_bus=spi_bus, cs=cs_pin)
            self._sdcard.info()
            print("SD card initialized successfully")
        except Exception as e:
            print(f"ERROR: Failed to initialize SD card: {e}")
            print("  - Possible causes: Invalid SPI configuration, SD card not inserted, faulty wiring, or firmware issue")
            print(f"  - Check: SPI pins for the SPI bus, card insertion, VCC (3.3V/5V), GND")
            print("  - Try: Hard reset ESP32, test with known-good SD card")

    def _try_mount(self, mount_point):
        try:
            os.mount(self._sdcard, mount_point)
            print(f"SD card mounted successfully at {mount_point}")
            return True
        except OSError as e:
            if e.errno == errno.EPERM:  # EPERM is 1, meaning already mounted
                print(f"Got mount error {e} which means already mounted.")
                return True
            else:
                print(f"WARNING: Failed to mount SD card at {mount_point}: {e}")
                print("  - Possible causes: Unformatted SD card (needs FAT32), corrupted filesystem, or card removed")
                print(f"  - Check: SD card format, ensure card is inserted")
                print("  - Try: Format card on PC, or proceed to auto-format if enabled")
                return False

    def _format(self, mount_point):
        try:
            print(f"Attempting to format SD card for {mount_point}...")
            try:
                os.umount(mount_point)
                print(f"  - Unmounted {mount_point} (if it was mounted)")
            except OSError:
                print(f"  - No prior mount found for {mount_point}, proceeding with format")
            vfs.VfsFat.mkfs(self._sdcard)
            print("SD card formatted successfully as FAT32")
            return True
        except OSError as e:
            print(f"ERROR: Failed to format SD card: {e}")
            print("  - Possible causes: SD card not inserted, write-protected, incompatible, or hardware error")
            print(f"  - Check: Card insertion, write-protect switch, verify wiring of SPI bus.")
            print("  - Try: Test with another SD card, reformat on PC, ensure VCC/GND correct")
            return False

    def mount_with_optional_format(self, mount_point):
        if not self._sdcard:
            print(f"ERROR: No SD card object initialized for mounting at {mount_point}")
            print("  - Possible causes: SD card initialization failed in __init__")
            print("  - Check: Review initialization errors above, verify SPI setup and hardware")
            print("  - Try: Hard reset, check SPI pins and SD card")
            return False

        if not self._try_mount(mount_point):
            print(f"INFO: Initial mount failed at {mount_point}, attempting to format...")
            if self._format(mount_point):
                if not self._try_mount(mount_point):
                    print(f"ERROR: Failed to mount SD card at {mount_point} even after formatting")
                    print("  - Possible causes: Persistent hardware issue, incompatible SD card, or firmware bug")
                    print(f"  - Check: Wiring of SPI bus and card type.")
                    print("  - Try: Hard reset, test with different SD card, reflash firmware")
                    return False
            else:
                print(f"ERROR: Could not format SD card for {mount_point} - mount aborted")
                print("  - See format error details above for troubleshooting")
                return False

        try:
            contents = os.listdir(mount_point)
            print(f"SD card contents at {mount_point}: {contents}")
            return True
        except OSError as e:
            print(f"WARNING: Could not list SD card contents at {mount_point}: {e}")
            print("  - Possible causes: Filesystem corruption, card removed, or VFS cache issue")
            print(f"  - Check: Ensure card is inserted, verify mount with is_mounted('{mount_point}')")
            print("  - Try: Unmount and remount, or reformat card")
            return False

    def is_mounted(self, mount_point):
        try:
            mounted = mount_point in os.listdir('/') and not os.mkdir(f'{mount_point}/_tmp_test')
            if mounted:
                print(f"SD card is mounted at {mount_point}")
                try:
                    os.rmdir(f'{mount_point}/_tmp_test')
                except:
                    pass
            else:
                print(f"SD card is not mounted at {mount_point}")
                print("  - Possible causes: Never mounted, unmounted manually, or card removed")
                print(f"  - Try: Call mount_with_optional_format('{mount_point}')")
            return mounted
        except OSError as e:
            print(f"WARNING: Failed to check mount status at {mount_point}: {e}")
            print("  - Possible causes: Card removed, invalid mount point, or filesystem error")
            print(f"  - Check: Ensure {mount_point} exists and card is inserted")
            print("  - Try: Remount or reinsert card")
            return False

    def list(self, mount_point):
        try:
            contents = os.listdir(mount_point)
            print(f"SD card contents at {mount_point}: {contents}")
            return contents
        except OSError as e:
            print(f"WARNING: Failed to list contents at {mount_point}: {e}")
            print("  - Possible causes: SD card not mounted, removed, or corrupted filesystem")
            print(f"  - Check: Run is_mounted('{mount_point}'), ensure card is inserted")
            print("  - Try: Remount with mount_with_optional_format('{mount_point}')")
            return []

# --- Singleton pattern ---
_manager = None

def init(spi_bus, cs_pin):
    """Initialize the global SD card manager."""
    global _manager
    if _manager is None:
        _manager = SDCardManager(spi_bus, cs_pin)
    else:
        print("WARNING: SDCardManager already initialized")
        print("  - Use existing instance via get()")
    return _manager

def get():
    """Get the global SD card manager instance."""
    if _manager is None:
        print("ERROR: SDCardManager not initialized")
        print("  - Call init(spi_bus, cs_pin) first in boot.py or main.py")
    return _manager

def mount(mount_point):
    mgr = get()
    if mgr is None:
        print("ERROR: Cannot mount - SDCardManager not initialized")
        print("  - Call init(spi_bus, cs_pin) first")
        return False
    return mgr.mount(mount_point)

def mount_with_optional_format(mount_point):
    mgr = get()
    if mgr is None:
        print("ERROR: Cannot mount with format - SDCardManager not initialized")
        print("  - Call init(spi_bus, cs_pin) first")
        return False
    success = mgr.mount_with_optional_format(mount_point)
    if not success:
        print(f"ERROR: mount_with_format('{mount_point}') failed")
        print("  - See detailed errors above for mount or format issues")
    return success
