import logging
import os
import machine
import vfs

logger = logging.getLogger(__name__)

class SDCardManager:
    def __init__(self, mode=None, spi_bus=None, cs_pin=None, cmd_pin=None, clk_pin=None,
                 d0_pin=None, d1_pin=None, d2_pin=None, d3_pin=None, slot=1, width=None, freq=20000000):
        self._sdcard = None
        self._mode = None
        
        # Auto-detect mode: if SDIO pins provided, use SDIO; otherwise use SPI
        if cmd_pin is not None or clk_pin is not None or d0_pin is not None:
            self._mode = 'sdio'
        else:
            self._mode = 'spi'
        
        # Allow explicit mode override only if explicitly provided (not default)
        if mode is not None and mode in ('spi', 'sdio'):
            self._mode = mode
        
        if __debug__: logger.debug("SD card mode: %s", self._mode.upper())

        if self._mode == 'spi':
            self._init_spi(spi_bus, cs_pin)
        elif self._mode == 'sdio':
            self._init_sdio(cmd_pin, clk_pin, d0_pin, d1_pin, d2_pin, d3_pin, slot, width, freq)
    
    def _init_spi(self, spi_bus, cs_pin):
        """Initialize SD card in SPI mode."""
        if spi_bus is None or cs_pin is None:
            logger.error("SPI mode requires spi_bus and cs_pin parameters")
            if __debug__: logger.debug("  - Provide: init(spi_bus=machine.SPI(...), cs_pin=pin_number)")
            return
        
        try:
            self._sdcard = machine.SDCard(spi_bus=spi_bus, cs=cs_pin)
            self._sdcard.info()
            if __debug__: logger.debug("SD card initialized successfully in SPI mode")
        except Exception as e:
            logger.error("Failed to initialize SD card in SPI mode: %s", e)
            if __debug__: logger.debug("  - Possible causes: Invalid SPI configuration, SD card not inserted, faulty wiring, or firmware issue")
            if __debug__: logger.debug("  - Check: SPI pins for the SPI bus, card insertion, VCC (3.3V/5V), GND")
            if __debug__: logger.debug("  - Try: Hard reset ESP32, test with known-good SD card")
    
    def _init_sdio(self, cmd_pin, clk_pin, d0_pin, d1_pin=None, d2_pin=None, d3_pin=None,
                   slot=1, width=None, freq=20000000):
        """Initialize SD card in SDIO mode."""
        # Validate required SDIO parameters
        if cmd_pin is None or clk_pin is None or d0_pin is None:
            logger.error("SDIO mode requires cmd_pin, clk_pin, and d0_pin parameters")
            if __debug__: logger.debug("  - Provide: init(mode='sdio', cmd_pin=X, clk_pin=Y, d0_pin=Z, ...)")
            return
        
        # Auto-detect SDIO width based on provided data pins
        # This happens BEFORE explicit width validation to allow user override
        if width is None:
            # Count how many data pins are provided
            data_pins_provided = sum([
                d0_pin is not None,
                d1_pin is not None,
                d2_pin is not None,
                d3_pin is not None
            ])
            
            if data_pins_provided == 1:
                # Only d0_pin provided: use 1-bit mode
                width = 1
                if __debug__: logger.debug("Auto-detected SDIO width=1 (only d0_pin provided)")
            elif data_pins_provided == 4:
                # All four data pins provided: use 4-bit mode
                width = 4
                if __debug__: logger.debug("Auto-detected SDIO width=4 (all four data pins provided)")
            else:
                # Partial pins provided: this is an error
                logger.error("Invalid SDIO pin configuration - %s data pins provided", data_pins_provided)
                if __debug__: logger.debug("  - For 1-bit mode: provide only d0_pin")
                if __debug__: logger.debug("  - For 4-bit mode: provide all four pins (d0_pin, d1_pin, d2_pin, d3_pin)")
                if __debug__: logger.debug("  - Or explicitly specify width parameter to override auto-detection")
                return
        
        # Validate width parameter
        if width not in (1, 4):
            logger.error("SDIO width must be 1 or 4, got %s", width)
            return
        
        # Validate slot parameter
        if slot not in (0, 1):
            logger.error("SDIO slot must be 0 or 1, got %s", slot)
            return
        
        # Validate that provided pins match the requested width
        if width == 4:
            if d1_pin is None or d2_pin is None or d3_pin is None:
                logger.error("SDIO 4-bit mode requires all four data pins (d0_pin, d1_pin, d2_pin, d3_pin)")
                if __debug__: logger.debug("  - Provide all four data pins for 4-bit mode")
                if __debug__: logger.debug("  - Or use 1-bit mode with only d0_pin")
                return
        elif width == 1:
            if d1_pin is not None or d2_pin is not None or d3_pin is not None:
                logger.error("SDIO 1-bit mode should only have d0_pin, but extra pins were provided")
                if __debug__: logger.debug("  - For 1-bit mode: provide only d0_pin")
                if __debug__: logger.debug("  - For 4-bit mode: provide all four pins (d0_pin, d1_pin, d2_pin, d3_pin)")
                return
        
        try:
            # For 4-bit mode, all data pins are required
            if width == 4:
                self._sdcard = machine.SDCard(
                    slot=slot,
                    cmd=cmd_pin,
                    clk=clk_pin,
                    data_pins=(d0_pin,d1_pin,d2_pin,d3_pin,),
                    width=width,
                    freq=freq
                )
            else:  # 1-bit mode
                self._sdcard = machine.SDCard(
                    slot=slot,
                    cmd=cmd_pin,
                    clk=clk_pin,
                    data_pins=(d0_pin,),
                    width=width,
                    freq=freq
                )
            
            self._sdcard.info()
            if __debug__: logger.debug("SD card initialized successfully in SDIO mode (slot=%s, width=%s-bit, freq=%sHz)", slot, width, freq)
        except Exception as e:
            logger.error("Failed to initialize SD card in SDIO mode: %s", e)
            if __debug__: logger.debug("  - Possible causes: Invalid SDIO pin configuration, SD card not inserted, faulty wiring, or firmware issue")
            if __debug__: logger.debug("  - Check: SDIO pins (CMD, CLK, D0-D3), card insertion, VCC (3.3V), GND")
            if __debug__: logger.debug("  - Try: Hard reset ESP32, verify pin assignments, test with known-good SD card")

    def _try_mount(self, mount_point):
        try:
            os.mount(self._sdcard, mount_point)
            if __debug__: logger.debug("SD card mounted successfully at %s", mount_point)
            return True
        except OSError as e:
            import errno
            if e.errno == errno.EPERM:  # EPERM is 1, meaning already mounted
                if __debug__: logger.debug("Got mount error %s which means already mounted.", e)
                return True
            else:
                logger.warning("Failed to mount SD card at %s: %s", mount_point, e)
                if __debug__: logger.debug("  - Possible causes: Unformatted SD card (needs FAT32), corrupted filesystem, or card removed")
                if __debug__: logger.debug("  - Check: SD card format, ensure card is inserted")
                if __debug__: logger.debug("  - Try: Format card on PC, or proceed to auto-format if enabled")
                return False

    def _format(self, mount_point):
        try:
            if __debug__: logger.debug("Attempting to format SD card for %s...", mount_point)
            try:
                os.umount(mount_point)
                if __debug__: logger.debug("  - Unmounted %s (if it was mounted)", mount_point)
            except OSError:
                if __debug__: logger.debug("  - No prior mount found for %s, proceeding with format", mount_point)
            vfs.VfsFat.mkfs(self._sdcard)
            if __debug__: logger.debug("SD card formatted successfully as FAT32")
            return True
        except OSError as e:
            logger.error("Failed to format SD card: %s", e)
            if __debug__: logger.debug("  - Possible causes: SD card not inserted, write-protected, incompatible, or hardware error")
            if __debug__: logger.debug("  - Check: Card insertion, write-protect switch, verify wiring of SPI bus.")
            if __debug__: logger.debug("  - Try: Test with another SD card, reformat on PC, ensure VCC/GND correct")
            return False

    def mount_with_optional_format(self, mount_point):
        if not self._sdcard:
            logger.error("No SD card object initialized for mounting at %s", mount_point)
            if __debug__: logger.debug("  - Possible causes: SD card initialization failed in __init__")
            if __debug__: logger.debug("  - Check: Review initialization errors above, verify SPI setup and hardware")
            if __debug__: logger.debug("  - Try: Hard reset, check SPI pins and SD card")
            return False

        if not self._try_mount(mount_point):
            if __debug__: logger.debug("Initial mount failed at %s, attempting to format...", mount_point)
            if self._format(mount_point):
                if not self._try_mount(mount_point):
                    logger.error("Failed to mount SD card at %s even after formatting", mount_point)
                    if __debug__: logger.debug("  - Possible causes: Persistent hardware issue, incompatible SD card, or firmware bug")
                    if __debug__: logger.debug("  - Check: Wiring of SPI bus and card type.")
                    if __debug__: logger.debug("  - Try: Hard reset, test with different SD card, reflash firmware")
                    return False
            else:
                logger.error("Could not format SD card for %s - mount aborted", mount_point)
                if __debug__: logger.debug("  - See format error details above for troubleshooting")
                return False

        try:
            # FAT32 rejects directory paths ending with '/' for os.listdir().
            contents = os.listdir(mount_point.rstrip("/") or "/")
            if __debug__: logger.debug("SD card contents at %s: %s", mount_point, contents)
            return True
        except OSError as e:
            logger.warning("Could not list SD card contents at %s: %s", mount_point, e)
            if __debug__: logger.debug("  - Possible causes: Filesystem corruption, card removed, or VFS cache issue")
            if __debug__: logger.debug("  - Check: Ensure card is inserted, verify mount with is_mounted('%s')", mount_point)
            if __debug__: logger.debug("  - Try: Unmount and remount, or reformat card")
            return False

    def is_mounted(self, mount_point):
        try:
            mounted = mount_point in os.listdir('/') and not os.mkdir(f'{mount_point}/_tmp_test')
            if mounted:
                if __debug__: logger.debug("SD card is mounted at %s", mount_point)
                try:
                    os.rmdir(f'{mount_point}/_tmp_test')
                except:
                    pass
            else:
                if __debug__: logger.debug("SD card is not mounted at %s", mount_point)
                if __debug__: logger.debug("  - Possible causes: Never mounted, unmounted manually, or card removed")
                if __debug__: logger.debug("  - Try: Call mount_with_optional_format('%s')", mount_point)
            return mounted
        except OSError as e:
            logger.warning("Failed to check mount status at %s: %s", mount_point, e)
            if __debug__: logger.debug("  - Possible causes: Card removed, invalid mount point, or filesystem error")
            if __debug__: logger.debug("  - Check: Ensure %s exists and card is inserted", mount_point)
            if __debug__: logger.debug("  - Try: Remount or reinsert card")
            return False

    def list(self, mount_point):
        try:
            # FAT32 rejects directory paths ending with '/' for os.listdir().
            contents = os.listdir(mount_point.rstrip("/") or "/")
            if __debug__: logger.debug("SD card contents at %s: %s", mount_point, contents)
            return contents
        except OSError as e:
            logger.warning("Failed to list contents at %s: %s", mount_point, e)
            if __debug__: logger.debug("  - Possible causes: SD card not mounted, removed, or corrupted filesystem")
            if __debug__: logger.debug("  - Check: Run is_mounted('%s'), ensure card is inserted", mount_point)
            if __debug__: logger.debug("  - Try: Remount with mount_with_optional_format('%s')", mount_point)
            return []

# --- Singleton pattern ---
_manager = None

def init(mode=None, spi_bus=None, cs_pin=None, cmd_pin=None, clk_pin=None,
         d0_pin=None, d1_pin=None, d2_pin=None, d3_pin=None, slot=1, width=None, freq=20000000):
    """
    Initialize the global SD card manager.
    
    SPI mode (default):
        init(spi_bus=machine.SPI(...), cs_pin=pin_number)
    
    SDIO mode with auto-detection:
        init(mode='sdio', cmd_pin=X, clk_pin=Y, d0_pin=Z, d1_pin=A, d2_pin=B, d3_pin=C, slot=1, freq=20000000)
    
    SDIO width auto-detection:
        - If only d0_pin is provided: width is auto-set to 1 (1-bit mode)
        - If all four data pins (d0, d1, d2, d3) are provided: width is auto-set to 4 (4-bit mode)
        - If width parameter is explicitly provided: that value is used (overrides auto-detection)
        - If partial data pins are provided (e.g., only d0 and d1): raises an error
    
    Auto-detection of mode:
        If SDIO pins are provided, SDIO mode is used automatically.
    """
    global _manager
    if _manager is None:
        _manager = SDCardManager(
            mode=mode,
            spi_bus=spi_bus,
            cs_pin=cs_pin,
            cmd_pin=cmd_pin,
            clk_pin=clk_pin,
            d0_pin=d0_pin,
            d1_pin=d1_pin,
            d2_pin=d2_pin,
            d3_pin=d3_pin,
            slot=slot,
            width=width,
            freq=freq
        )
    else:
        logger.warning("SDCardManager already initialized")
        if __debug__: logger.debug("  - Use existing instance via get()")
    return _manager

def get():
    """Get the global SD card manager instance."""
    if _manager is None:
        logger.error("SDCardManager not initialized")
        if __debug__: logger.debug("  - Call init() with appropriate parameters first in lib/mpos/board/*.py")
        if __debug__: logger.debug("  - SPI mode: init(spi_bus=machine.SPI(...), cs_pin=pin_number)")
        if __debug__: logger.debug("  - SDIO mode: init(mode='sdio', cmd_pin=X, clk_pin=Y, d0_pin=Z, ...)")
    return _manager

def get_mode():
    """Get the current SD card mode ('spi' or 'sdio')."""
    mgr = get()
    if mgr is None:
        logger.error("Cannot get mode - SDCardManager not initialized")
        return None
    return mgr._mode

def mount(mount_point):
    mgr = get()
    if mgr is None:
        logger.error("Cannot mount - SDCardManager not initialized")
        if __debug__: logger.debug("  - Call init() with appropriate parameters first")
        return False
    return mgr.mount_with_optional_format(mount_point)

def mount_with_optional_format(mount_point):
    mgr = get()
    if mgr is None:
        logger.error("Cannot mount with format - SDCardManager not initialized")
        if __debug__: logger.debug("  - Call init() with appropriate parameters first")
        return False
    success = mgr.mount_with_optional_format(mount_point)
    if not success:
        logger.error("mount_with_format('%s') failed", mount_point)
        if __debug__: logger.debug("  - See detailed errors above for mount or format issues")
    return success
