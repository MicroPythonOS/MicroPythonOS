import os
import machine
import vfs

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
        
        print(f"SD card mode: {self._mode.upper()}")
        
        if self._mode == 'spi':
            self._init_spi(spi_bus, cs_pin)
        elif self._mode == 'sdio':
            self._init_sdio(cmd_pin, clk_pin, d0_pin, d1_pin, d2_pin, d3_pin, slot, width, freq)
    
    def _init_spi(self, spi_bus, cs_pin):
        """Initialize SD card in SPI mode."""
        if spi_bus is None or cs_pin is None:
            print("ERROR: SPI mode requires spi_bus and cs_pin parameters")
            print("  - Provide: init(spi_bus=machine.SPI(...), cs_pin=pin_number)")
            return
        
        try:
            self._sdcard = machine.SDCard(spi_bus=spi_bus, cs=cs_pin)
            self._sdcard.info()
            print("SD card initialized successfully in SPI mode")
        except Exception as e:
            print(f"ERROR: Failed to initialize SD card in SPI mode: {e}")
            print("  - Possible causes: Invalid SPI configuration, SD card not inserted, faulty wiring, or firmware issue")
            print(f"  - Check: SPI pins for the SPI bus, card insertion, VCC (3.3V/5V), GND")
            print("  - Try: Hard reset ESP32, test with known-good SD card")
    
    def _init_sdio(self, cmd_pin, clk_pin, d0_pin, d1_pin=None, d2_pin=None, d3_pin=None,
                   slot=1, width=None, freq=20000000):
        """Initialize SD card in SDIO mode."""
        # Validate required SDIO parameters
        if cmd_pin is None or clk_pin is None or d0_pin is None:
            print("ERROR: SDIO mode requires cmd_pin, clk_pin, and d0_pin parameters")
            print("  - Provide: init(mode='sdio', cmd_pin=X, clk_pin=Y, d0_pin=Z, ...)")
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
                print("INFO: Auto-detected SDIO width=1 (only d0_pin provided)")
            elif data_pins_provided == 4:
                # All four data pins provided: use 4-bit mode
                width = 4
                print("INFO: Auto-detected SDIO width=4 (all four data pins provided)")
            else:
                # Partial pins provided: this is an error
                print(f"ERROR: Invalid SDIO pin configuration - {data_pins_provided} data pins provided")
                print("  - For 1-bit mode: provide only d0_pin")
                print("  - For 4-bit mode: provide all four pins (d0_pin, d1_pin, d2_pin, d3_pin)")
                print("  - Or explicitly specify width parameter to override auto-detection")
                return
        
        # Validate width parameter
        if width not in (1, 4):
            print(f"ERROR: SDIO width must be 1 or 4, got {width}")
            return
        
        # Validate slot parameter
        if slot not in (0, 1):
            print(f"ERROR: SDIO slot must be 0 or 1, got {slot}")
            return
        
        # Validate that provided pins match the requested width
        if width == 4:
            if d1_pin is None or d2_pin is None or d3_pin is None:
                print("ERROR: SDIO 4-bit mode requires all four data pins (d0_pin, d1_pin, d2_pin, d3_pin)")
                print("  - Provide all four data pins for 4-bit mode")
                print("  - Or use 1-bit mode with only d0_pin")
                return
        elif width == 1:
            if d1_pin is not None or d2_pin is not None or d3_pin is not None:
                print("ERROR: SDIO 1-bit mode should only have d0_pin, but extra pins were provided")
                print("  - For 1-bit mode: provide only d0_pin")
                print("  - For 4-bit mode: provide all four pins (d0_pin, d1_pin, d2_pin, d3_pin)")
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
            print(f"SD card initialized successfully in SDIO mode (slot={slot}, width={width}-bit, freq={freq}Hz)")
        except Exception as e:
            print(f"ERROR: Failed to initialize SD card in SDIO mode: {e}")
            print("  - Possible causes: Invalid SDIO pin configuration, SD card not inserted, faulty wiring, or firmware issue")
            print(f"  - Check: SDIO pins (CMD, CLK, D0-D3), card insertion, VCC (3.3V), GND")
            print("  - Try: Hard reset ESP32, verify pin assignments, test with known-good SD card")

    def _try_mount(self, mount_point):
        try:
            os.mount(self._sdcard, mount_point)
            print(f"SD card mounted successfully at {mount_point}")
            return True
        except OSError as e:
            import errno
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
        print("WARNING: SDCardManager already initialized")
        print("  - Use existing instance via get()")
    return _manager

def get():
    """Get the global SD card manager instance."""
    if _manager is None:
        print("ERROR: SDCardManager not initialized")
        print("  - Call init() with appropriate parameters first in lib/mpos/board/*.py")
        print("  - SPI mode: init(spi_bus=machine.SPI(...), cs_pin=pin_number)")
        print("  - SDIO mode: init(mode='sdio', cmd_pin=X, clk_pin=Y, d0_pin=Z, ...)")
    return _manager

def get_mode():
    """Get the current SD card mode ('spi' or 'sdio')."""
    mgr = get()
    if mgr is None:
        print("ERROR: Cannot get mode - SDCardManager not initialized")
        return None
    return mgr._mode

def mount(mount_point):
    mgr = get()
    if mgr is None:
        print("ERROR: Cannot mount - SDCardManager not initialized")
        print("  - Call init() with appropriate parameters first")
        return False
    return mgr.mount_with_optional_format(mount_point)

def mount_with_optional_format(mount_point):
    mgr = get()
    if mgr is None:
        print("ERROR: Cannot mount with format - SDCardManager not initialized")
        print("  - Call init() with appropriate parameters first")
        return False
    success = mgr.mount_with_optional_format(mount_point)
    if not success:
        print(f"ERROR: mount_with_format('{mount_point}') failed")
        print("  - See detailed errors above for mount or format issues")
    return success
