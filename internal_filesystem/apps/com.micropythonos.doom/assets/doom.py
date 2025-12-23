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

    def onCreate(self):
        screen = lv.obj()
        self.status_label = lv.label(screen)
        self.status_label.set_width(lv.pct(90))
        self.status_label.set_text(f'Looking for .wad or .zip files in {self.doomdir} on internal storage and SD card...')
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.center()
        self.setContentView(screen)

    def onResume(self, screen):
        # Try to mount the SD card and if successful, use it, as retro-go can only use one or the other:
        bootfile_prefix = ""
        mounted_sdcard = sdcard.mount_with_optional_format(self.mountpoint_sdcard)
        if mounted_sdcard:
            print("sdcard is mounted, configuring it...")
            bootfile_prefix = self.mountpoint_sdcard
        bootfile_to_write = bootfile_prefix + self.bootfile
        print(f"writing to {bootfile_to_write}")
        # Do it in a separate task so the UI doesn't hang (shows progress, status_label) and the serial console keeps showing prints
        TaskManager.create_task(self.start_wad(bootfile_prefix, bootfile_to_write, self.doomdir + '/Doom v1.9 Free Shareware.zip'))

    def mkdir(self, dirname):
        # Would be better to only create it if it doesn't exist
        try:
            import os
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
            import os
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
