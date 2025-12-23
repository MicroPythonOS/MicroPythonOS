import lvgl as lv
import os
from mpos.apps import Activity
from mpos import TaskManager, sdcard

class Doom(Activity):

    romdir = "/roms"
    doomdir = romdir + "/doom"
    retrogodir = "/retro-go"
    configdir = retrogodir + "/config"
    bootfile = configdir + "/boot.json"
    partition_label = "prboom-go"
    mountpoint_sdcard = "/sdcard"
    esp32_partition_type_ota_0 = 16
    #partition_label = "retro-core"
    # Widgets:
    status_label = None
    wadlist = None
    bootfile_prefix = ""
    bootfile_to_write = ""

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_pad_all(15, 0)
        
        # Create title label
        title_label = lv.label(screen)
        title_label.set_text("Choose your DOOM:")
        title_label.align(lv.ALIGN.TOP_LEFT, 0, 0)

        # Create list widget for WAD files
        self.wadlist = lv.list(screen)
        self.wadlist.set_size(lv.pct(100), lv.pct(70))
        self.wadlist.center()

        # Create status label for messages
        self.status_label = lv.label(screen)
        self.status_label.set_width(lv.pct(90))
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        # Set default green color for status label
        self.status_label.set_style_text_color(lv.color_hex(0x00FF00), 0)

        self.setContentView(screen)

    def onResume(self, screen):
        # Try to mount the SD card and if successful, use it, as retro-go can only use one or the other:
        self.bootfile_prefix = ""
        mounted_sdcard = sdcard.mount_with_optional_format(self.mountpoint_sdcard)
        if mounted_sdcard:
            print("sdcard is mounted, configuring it...")
            self.bootfile_prefix = self.mountpoint_sdcard
        self.bootfile_to_write = self.bootfile_prefix + self.bootfile
        print(f"writing to {self.bootfile_to_write}")
        
        # Scan for WAD files and populate the list
        self.refresh_wad_list()

    def scan_wad_files(self, directory):
        """Scan a directory for .wad and .zip files"""
        wad_files = []
        try:
            for filename in os.listdir(directory):
                if filename.lower().endswith(('.wad', '.zip')):
                    wad_files.append(filename)
            
            # Sort the list for consistent ordering
            wad_files.sort()
            print(f"Found {len(wad_files)} WAD files in {directory}: {wad_files}")
        except OSError as e:
            print(f"Directory does not exist or cannot be read: {directory}")
        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")
        
        return wad_files

    def get_file_size_warning(self, filepath):
        """Get file size warning suffix if file is too small or empty"""
        try:
            size = os.stat(filepath)[6]  # Get file size
            if size == 0:
                return " (EMPTY FILE)"  # Red
            elif size < 80 * 1024:  # 80KB
                return " (TOO SMALL)"  # Orange
        except Exception as e:
            print(f"Error checking file size for {filepath}: {e}")
        return ""

    def refresh_wad_list(self):
        self.status_label.set_text(f"Listing files in: {self.bootfile_prefix + self.doomdir}")
        """Scan for WAD files and populate the list"""
        print("refresh_wad_list: Clearing current list")
        self.wadlist.clean()

        # Scan internal storage or SD card
        all_wads = self.scan_wad_files(self.bootfile_prefix + self.doomdir)
        all_wads.sort()

        if len(all_wads) == 0:
            self.status_label.set_text(f"No .wad or .zip files found in {self.doomdir}")
            print("No WAD files found")
            return

        # If only one WAD file, auto-start it
        if len(all_wads) == 1:
            print(f"refresh_wad_list: Only one WAD file found, auto-starting: {all_wads[0]}")
            self.start_wad_file(all_wads[0])
            return

        # Populate list with WAD files
        print(f"refresh_wad_list: Populating list with {len(all_wads)} WAD files")
        self.status_label.set_text(f"Listed files in: {self.bootfile_prefix + self.doomdir}")
        for wad_file in all_wads:
            # Get file size warning if applicable
            warning = self.get_file_size_warning(self.doomdir + '/' + wad_file)
            button_text = wad_file + warning
            button = self.wadlist.add_button(None, button_text)
            button.add_event_cb(lambda e, f=wad_file: self.start_wad_file(f), lv.EVENT.CLICKED, None)

    def start_wad_file(self, wad_file):
        """Start a WAD file (called from list selection or auto-start)"""
        print(f"start_wad_file: WAD file selected: {wad_file}")
        wadfile_path = self.doomdir + '/' + wad_file
        # Do it in a separate task so the UI doesn't hang (shows progress, status_label) and the serial console keeps showing prints
        TaskManager.create_task(self.start_wad(self.bootfile_prefix, self.bootfile_to_write, wadfile_path))

    def mkdir(self, dirname):
        # Would be better to only create it if it doesn't exist
        try:
            os.mkdir(dirname)
        except Exception as e:
            # Not really useful to show this in the UI, as it's usually just an "already exists" error:
            print(f"Info: could not create directory {dirname} because: {e}")

    async def start_wad(self, bootfile_prefix, bootfile_to_write, wadfile):
        self.status_label.set_text(f"Launching Doom with file: {bootfile_prefix}{wadfile}")
        await TaskManager.sleep(1) # Give the user a minimal amount of time to read the filename

        # Create these folders, in case the user wants to add doom later:
        self.mkdir(bootfile_prefix + self.romdir)
        self.mkdir(bootfile_prefix + self.doomdir)

        # Create structure to place bootfile:
        self.mkdir(bootfile_prefix + self.retrogodir)
        self.mkdir(bootfile_prefix + self.configdir)
        try:
            import json
            # Would be better to only write this if it differs from what's already there:
            fd = open(bootfile_to_write, 'w')
            bootconfig = {
                "BootName": "doom",
                "BootArgs": f"/sd{wadfile}",
                "BootSlot": -1,
                "BootFlags": 0
            }
            json.dump(bootconfig, fd)
            fd.close()
        except Exception as e:
            self.status_label.set_text(f"ERROR: could not write config file: {e}")
            return
        results = []
        try:
            from esp32 import Partition
            results = Partition.find(label=self.partition_label)
        except Exception as e:
            self.status_label.set_text(f"ERROR: could not search for internal partition with label {self.partition_label}, unable to start: {e}")
            return
        if len(results) < 1:
            self.status_label.set_text(f"ERROR: could not find internal partition with label {self.partition_label}, unable to start")
            return
        partition = results[0]
        try:
            partition.set_boot()
        except Exception as e:
            print(f"ERROR: could not set partition {partition} as boot, it probably doesn't contain a valid program: {e}")
        try:
            import vfs
            vfs.umount('/')
        except Exception as e:
            print(f"Warning: could not unmount internal filesystem from /: {e}")
        # Write the currently booted OTA partition number to NVS, so that retro-go's apps know where to go back to:
        try:
            from esp32 import NVS
            nvs = NVS('fri3d.sys')
            boot_partition = nvs.get_i32('boot_partition')
            print(f"boot_partition in fri3d.sys of NVS: {boot_partition}")
            running_partition = Partition(Partition.RUNNING)
            running_partition_nr = running_partition.info()[1] - self.esp32_partition_type_ota_0
            print(f"running_partition_nr: {running_partition_nr}")
            if running_partition_nr != boot_partition:
                print(f"setting boot_partition in fri3d.sys of NVS to {running_partition_nr}")
                nvs.set_i32('boot_partition', running_partition_nr)
            else:
                print("No need to update boot_partition")
        except Exception as e:
            print(f"Warning: could not write currently booted partition to boot_partition in fri3d.sys of NVS: {e}")
        try:
            import machine
            machine.reset()
        except Exception as e:
            print(f"Warning: could not restart machine: {e}")
