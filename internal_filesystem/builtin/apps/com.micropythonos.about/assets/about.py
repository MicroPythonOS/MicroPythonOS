import sys
import logging

from mpos import Activity, DisplayMetrics, BuildInfo, DeviceInfo

class About(Activity):

    logger = logging.getLogger(__file__)
    logger.setLevel(logging.INFO)

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_border_width(0, lv.PART.MAIN)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        # Make the screen focusable so it can be scrolled with the arrow keys
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(screen)

        # Logo
        img = lv.image(screen)
        img.set_src("M:builtin/res/mipmap-mdpi/MicroPythonOS-logo-white-long-w296.png") # from the MPOS-logo repo
        img.set_blend_mode(lv.BLEND_MODE.DIFFERENCE)

        # Basic OS info
        self._add_label(screen, f"{lv.SYMBOL.HOME} Build Information", is_header=True, margin_top=0) # close to logo
        self._add_label(screen, f"Release version: {BuildInfo.version.release}")
        self._add_label(screen, f"API Level: {BuildInfo.version.api_level}")
        self._add_label(screen, f"Hardware ID: {DeviceInfo.hardware_id}")
        self._add_label(screen, f"sys.version: {sys.version}")
        self._add_label(screen, f"sys.implementation: {sys.implementation}")
        self._add_label(screen, f"sys.byteorder: {sys.byteorder}")
        self._add_label(screen, f"sys.maxsize of integer: {sys.maxsize}")

        # Platform info
        self._add_label(screen, f"{lv.SYMBOL.FILE} Platform", is_header=True)
        self._add_label(screen, f"sys.platform: {sys.platform}")
        self._add_label(screen, f"sys.path: {sys.path}")

        # MPY version info
        self._add_label(screen, f"{lv.SYMBOL.SETTINGS} Binary MPY Format", is_header=True)
        sys_mpy = sys.implementation._mpy
        self._add_label(screen, f'mpy version: {sys_mpy & 0xff}')
        self._add_label(screen, f'mpy sub-version: {sys_mpy >> 8 & 3}')
        arch = [None, 'x86', 'x64',
            'armv6', 'armv6m', 'armv7m', 'armv7em', 'armv7emsp', 'armv7emdp',
            'xtensa', 'xtensawin', 'rv32imc', 'rv64imc'][(sys_mpy >> 10) & 0x0F]
        flags = ""
        if arch:
            flags += ' -march=' + arch
        if (sys_mpy >> 16) != 0:
            flags += ' -march-flags=' + (sys_mpy >> 16)
        if len(flags) > 0:
            self._add_label(screen, 'mpy flags: ' + flags)

        # MicroPython and memory info
        self._add_label(screen, f"{lv.SYMBOL.DRIVE} Memory & Performance", is_header=True)
        import micropython
        self._add_label(screen, f"micropython.opt_level(): {micropython.opt_level()}")
        import gc
        self._add_label(screen, f"Memory: {gc.mem_free()} free, {gc.mem_alloc()} allocated, {gc.mem_alloc()+gc.mem_free()} total")
        # These are always written to sys.stdout
        #self._add_label(screen, f"micropython.mem_info(): {micropython.mem_info()}")
        #self._add_label(screen, f"micropython.qstr_info(): {micropython.qstr_info()}")
        import mpos
        self._add_label(screen, f"mpos.__path__: {mpos.__path__}") # this will show .frozen if the /lib folder is frozen (prod build)

        # ESP32 hardware info
        if sys.platform == "esp32":
            try:
                self._add_label(screen, f"{lv.SYMBOL.SETTINGS} ESP32 Hardware", is_header=True)
                import esp32
                self._add_label(screen, f"Temperature: {esp32.mcu_temperature()} °C")
            except Exception as e:
                self.logger.warning(f"Could not get ESP32 hardware info: {e}")

            # Machine info
            try:
                self.logger.info("Trying to find out additional board info, not available on every platform...")
                self._add_label(screen, f"{lv.SYMBOL.POWER} Machine Info", is_header=True)
                import machine
                self._add_label(screen, f"machine.freq: {machine.freq()}")
                # Format unique_id as MAC address (AA:BB:CC:DD:EE:FF)
                unique_id = machine.unique_id()
                mac_address = ':'.join(f'{b:02X}' for b in unique_id)
                self._add_label(screen, f"machine.unique_id(): {mac_address}")
                self._add_label(screen, f"machine.wake_reason(): {machine.wake_reason()}")
                self._add_label(screen, f"machine.reset_cause(): {machine.reset_cause()}")
            except Exception as e:
                error = f"Could not find machine info because: {e}\nIt's normal to get this error on desktop."
                self.logger.warning(error)
                self._add_label(screen, error)

            # Partition info (ESP32 only)
            try:
                self._add_label(screen, f"{lv.SYMBOL.SD_CARD} Partition Info", is_header=True)
                from esp32 import Partition
                current = Partition(Partition.RUNNING)
                self._add_label(screen, f"Partition.RUNNING: {current}")
                next_partition = current.get_next_update()
                self._add_label(screen, f"Next update partition: {next_partition}")
            except Exception as e:
                error = f"Could not find partition info because: {e}\nIt's normal to get this error on desktop."
                self.logger.warning(error)
                self._add_label(screen, error)

            # Network info (ESP32 only)
            try:
                self._add_label(screen, f"{lv.SYMBOL.WIFI} Network Info", is_header=True)
                from mpos import WifiService
                self._add_label(screen, f"IPv4 Address: {WifiService.get_ipv4_address()}")
                self._add_label(screen, f"IPv4 Gateway: {WifiService.get_ipv4_gateway()}")
            except Exception as e:
                error = f"Could not find network info because: {e}"
                self.logger.warning(error)
                self._add_label(screen, error)


        # Freezefs info (production builds only)
        try:
            self.logger.info("Trying to find out freezefs info")
            self._add_label(screen, f"{lv.SYMBOL.DOWNLOAD} Frozen Filesystem", is_header=True)
            import freezefs_mount_builtin
            self._add_label(screen, f"freezefs_mount_builtin.date_frozen: {freezefs_mount_builtin.date_frozen}")
            self._add_label(screen, f"freezefs_mount_builtin.files_folders: {freezefs_mount_builtin.files_folders}")
            self._add_label(screen, f"freezefs_mount_builtin.sum_size: {freezefs_mount_builtin.sum_size}")
            self._add_label(screen, f"freezefs_mount_builtin.version: {freezefs_mount_builtin.version}")
        except Exception as e:
            # This will throw an EEXIST exception if there is already a "/builtin" folder present
            # It will throw "no module named 'freezefs_mount_builtin'" if there is no frozen filesystem
            # It's possible that the user had a dev build with a non-frozen /buitin folder in the vfat storage partition,
            # and then they install a prod build (with OSUpdate) that then is unable to mount the freezefs into /builtin
            # BUT which will still have the frozen-inside /lib folder. So the user will be able to install apps into /builtin
            # but they will not be able to install libraries into /lib.
            error = f"Could not get freezefs_mount_builtin info because: {e}\nIt's normal to get an exception if the internal storage partition contains an overriding /builtin folder."
            self.logger.warning(error)
            self._add_label(screen, error)

        # Display info
        try:
            self._add_label(screen, f"{lv.SYMBOL.IMAGE} Display", is_header=True)
            hor_res = DisplayMetrics.width()
            ver_res = DisplayMetrics.height()
            self._add_label(screen, f"Resolution: {hor_res}x{ver_res}")
            dpi = DisplayMetrics.dpi()
            self._add_label(screen, f"Dots Per Inch (dpi): {dpi}")
        except Exception as e:
            self.logger.warning(f"Could not get display info: {e}")

        # Disk usage info
        self._add_label(screen, f"{lv.SYMBOL.DRIVE} Storage", is_header=True)
        self._add_disk_info(screen, '/')
        self._add_disk_info(screen, '/sdcard')

        self.setContentView(screen)

    @staticmethod
    def _focus_obj(event):
        target = event.get_target_obj()
        target.set_style_border_color(lv.theme_get_color_primary(None),lv.PART.MAIN)
        target.set_style_border_width(1, lv.PART.MAIN)
        target.scroll_to_view(True)

    @staticmethod
    def _defocus_obj(event):
        target = event.get_target_obj()
        target.set_style_border_width(0, lv.PART.MAIN)

    def _add_label(self, parent, text, is_header=False, margin_top=DisplayMetrics.pct_of_height(5)):
        """Helper to create and add a label with text."""
        label = lv.label(parent)
        label.set_text(text)
        # Make labels focusable to allow scroll on devices without touch screen
        label.add_event_cb(self._focus_obj, lv.EVENT.FOCUSED, None)
        label.add_event_cb(self._defocus_obj, lv.EVENT.DEFOCUSED, None)
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(label)
        if is_header:
            primary_color = lv.theme_get_color_primary(None)
            label.set_style_text_color(primary_color, lv.PART.MAIN)
            label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
            label.set_style_margin_top(margin_top, lv.PART.MAIN)
            label.set_style_margin_bottom(DisplayMetrics.pct_of_height(2), lv.PART.MAIN)
        else:
            label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
            label.set_style_margin_bottom(2, lv.PART.MAIN)
        return label

    def _add_disk_info(self, screen, path):
        """Helper to add disk usage info for a given path."""
        import os
        try:
            stat = os.statvfs(path)
            total_space = stat[0] * stat[2]
            free_space = stat[0] * stat[3]
            used_space = total_space - free_space
            self._add_label(screen, f"Total space {path}: {total_space} bytes")
            self._add_label(screen, f"Free space {path}: {free_space} bytes")
            self._add_label(screen, f"Used space {path}: {used_space} bytes")
        except Exception as e:
            self.logger.warning(f"About app could not get info on {path} filesystem: {e}")
