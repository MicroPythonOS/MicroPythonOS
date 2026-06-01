import lvgl as lv
import os
from mpos import Activity, Intent, SettingsActivity, SharedPreferences, TaskManager, sdcard


class RetroGoLauncher(Activity):

    mountpoint_sdcard = "/sdcard"
    esp32_partition_type_ota_0 = 16

    def onCreate(self):
        intent = self.getIntent()
        extras = intent.extras if intent else {}

        self.title = extras.get("title", "Choose file:")
        self.roms_subdir = extras.get("roms_subdir")
        self.partition_label = extras.get("partition_label")
        self.boot_name = extras.get("boot_name")
        self.game_name = extras.get("game_name", "Game")
        self.file_extensions = extras.get("file_extensions", (".wad", ".zip"))

        self.romdir = "/roms"
        self.retrogodir = "/retro-go"
        self.configdir = self.retrogodir + "/config"
        self.bootfile = self.configdir + "/boot.json"
        self.current_subdir = ""
        self._at_root_level = False
        self._launching = False

        screen = lv.obj()
        screen.set_style_pad_all(15, lv.PART.MAIN)

        title_label = lv.label(screen)
        title_label.set_text(self.title)
        title_label.align(lv.ALIGN.TOP_LEFT, 0, 0)

        self.wadlist = lv.list(screen)
        self.wadlist.set_size(lv.pct(100), lv.pct(70))
        self.wadlist.center()

        self.settings_button = lv.button(screen)
        settings_margin = 15
        settings_size = 44
        self.settings_button.set_size(settings_size, settings_size)
        self.settings_button.align(lv.ALIGN.TOP_RIGHT, -settings_margin, 10)
        self.settings_button.add_event_cb(self.settings_button_tap, lv.EVENT.CLICKED, None)
        settings_label = lv.label(self.settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
        settings_label.center()
        self.settings_button.move_to_index(-1)

        self.status_label = lv.label(screen)
        self.status_label.set_width(lv.pct(90))
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        self.status_label.set_style_text_color(lv.color_hex(0x00FF00), lv.PART.MAIN)

        self.setContentView(screen)

    def onResume(self, screen):
        self.bootfile_prefix = ""
        mounted_sdcard = sdcard.mount_with_optional_format(self.mountpoint_sdcard)
        if mounted_sdcard:
            print("sdcard is mounted, configuring it...")
            self.bootfile_prefix = self.mountpoint_sdcard
        self.bootfile_to_write = self.bootfile_prefix + self.bootfile
        print(f"writing to {self.bootfile_to_write}")

        self.refresh_file_list()

    def scan_entries(self, directory):
        subdirs = []
        matching_files = []
        try:
            for entry in os.ilistdir(directory):
                name = entry[0]
                if name.startswith("."):
                    continue

                mode = entry[1] if len(entry) > 1 else 0
                if mode & 0x4000:
                    subdirs.append(name)
                elif name.lower().endswith(self.file_extensions):
                    matching_files.append(name)
        except OSError:
            pass
        except AttributeError:
            try:
                for filename in os.listdir(directory):
                    if filename.startswith("."):
                        continue
                    if filename.lower().endswith(self.file_extensions):
                        matching_files.append(filename)
            except OSError:
                pass
            except Exception as e:
                print(f"Error scanning directory {directory}: {e}")
        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")

        subdirs.sort()
        matching_files.sort()
        print(f"Found {len(matching_files)} files in {directory}: {matching_files}")
        return subdirs, matching_files

    def refresh_file_list(self):
        if self._at_root_level:
            current_full_dir = self.bootfile_prefix + self.romdir
            self.status_label.set_text(f"Listing: {current_full_dir}")
            self.wadlist.clean()

            subdirs = []
            try:
                for entry in os.ilistdir(current_full_dir):
                    name = entry[0]
                    if name.startswith("."):
                        continue
                    mode = entry[1] if len(entry) > 1 else 0
                    if mode & 0x4000:
                        subdirs.append(name)
            except OSError:
                pass
            except AttributeError:
                try:
                    for filename in os.listdir(current_full_dir):
                        if filename.startswith("."):
                            continue
                        fullpath = current_full_dir + "/" + filename
                        if os.stat(fullpath)[0] & 0x4000:
                            subdirs.append(filename)
                except OSError:
                    pass
            subdirs.sort()

            if not subdirs:
                self.status_label.set_text("No ROM directories found")
                return

            for d in subdirs:
                button = self.wadlist.add_button(None, lv.SYMBOL.DIRECTORY + "  " + d)
                button.add_event_cb(lambda e, dirname=d: self.select_rom_subdir(dirname), lv.EVENT.CLICKED, None)
            return

        current_full_dir = self.bootfile_prefix + self.romdir + "/" + self.roms_subdir
        if self.current_subdir:
            current_full_dir += "/" + self.current_subdir

        self.status_label.set_text(f"Listing: {current_full_dir}")
        print(f"refresh_file_list: Clearing current list (dir={self.current_subdir})")
        self.wadlist.clean()

        subdirs, all_files = self.scan_entries(current_full_dir)

        if not subdirs and not all_files:
            self.status_label.set_text(f"No files found in {current_full_dir}")
            print("No files found")
            return

        print(f"refresh_file_list: {len(subdirs)} dirs, {len(all_files)} files")

        button = self.wadlist.add_button(None, "< Back")
        button.add_event_cb(lambda e: self.navigate_up(), lv.EVENT.CLICKED, None)

        for d in subdirs:
            button = self.wadlist.add_button(None, d + "/")
            button.add_event_cb(lambda e, dirname=d: self.navigate_into(dirname), lv.EVENT.CLICKED, None)

        for f in all_files:
            gamedir = self.romdir + "/" + self.roms_subdir
            fullpath = gamedir + "/" + self.current_subdir + "/" + f if self.current_subdir else gamedir + "/" + f
            button = self.wadlist.add_button(None, f)
            button.add_event_cb(
                lambda e, p=fullpath: self._launch_game(p),
                lv.EVENT.CLICKED, None
            )

    def navigate_into(self, subdir):
        if self.current_subdir:
            self.current_subdir += "/" + subdir
        else:
            self.current_subdir = subdir
        self.refresh_file_list()

    def navigate_up(self):
        if self.current_subdir:
            parts = self.current_subdir.split("/")
            parts.pop()
            self.current_subdir = "/".join(parts)
            self.refresh_file_list()
        elif not self._at_root_level:
            self._at_root_level = True
            self.refresh_file_list()

    def select_rom_subdir(self, dirname):
        self._at_root_level = False
        self.roms_subdir = dirname
        self.current_subdir = ""
        self.refresh_file_list()

    def settings_button_tap(self, event):
        prefs = SharedPreferences("retro-go")
        prefs.filepath = self.bootfile_prefix + self.retrogodir + "/config/global.json"
        prefs.filename = "global.json"
        prefs.load()
        for key in list(prefs.data.keys()):
            if not isinstance(prefs.data[key], str):
                prefs.data[key] = str(prefs.data[key])

        intent = Intent(activity_class=SettingsActivity)
        intent.putExtra("prefs", prefs)
        intent.putExtra("settings", [
            {
                "title": "Audio out",
                "key": "AudioDriver",
                "ui": "radiobuttons",
                "default_value": "buzzer",
                "ui_options": [
                    ("Buzzer", "buzzer"),
                    ("Ext DAC", "i2s"),
                ],
            },
            {
                "title": "Volume",
                "key": "Volume",
                "ui": "slider",
                "default_value": "50",
                "min": 0,
                "max": 100,
            },
        ])
        self.startActivity(intent)

    def mkdir(self, dirname):
        try:
            os.mkdir(dirname)
        except Exception as e:
            print(f"Info: could not create directory {dirname} because: {e}")

    def _launch_game(self, gamefile):
        if self._launching:
            return
        self._launching = True
        TaskManager.create_task(self.start_game(self.bootfile_prefix, self.bootfile_to_write, gamefile))

    async def start_game(self, bootfile_prefix, bootfile_to_write, gamefile):
        self.status_label.set_text(f"Launching {self.game_name} with file: {bootfile_prefix}{gamefile}")
        await TaskManager.sleep(1)

        self.mkdir(bootfile_prefix + self.romdir)
        self.mkdir(bootfile_prefix + self.romdir + "/" + self.roms_subdir)
        self.mkdir(bootfile_prefix + self.retrogodir)
        self.mkdir(bootfile_prefix + self.configdir)

        try:
            import json
            fd = open(bootfile_to_write, "w")
            bootconfig = {
                "BootName": self.boot_name,
                "BootArgs": f"/sd{gamefile}",
                "BootSlot": -1,
                "BootFlags": 0
            }
            print(f"Writing boot config: {bootconfig}")
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
            vfs.umount("/")
        except Exception as e:
            print(f"Warning: could not unmount internal filesystem from /: {e}")

        try:
            from esp32 import NVS
            nvs = NVS("fri3d.sys")
            try:
                boot_partition = nvs.get_i32("boot_partition")
                print(f"boot_partition in fri3d.sys of NVS: {boot_partition}")
            except OSError:
                boot_partition = -1
                print("boot_partition key not found in NVS, will create it")
            running_partition = Partition(Partition.RUNNING)
            running_partition_nr = running_partition.info()[1] - self.esp32_partition_type_ota_0
            print(f"running_partition_nr: {running_partition_nr}")
            if running_partition_nr != boot_partition:
                print(f"setting boot_partition in fri3d.sys of NVS to {running_partition_nr}")
                nvs.set_i32("boot_partition", running_partition_nr)
                try:
                    nvs.commit()
                except Exception:
                    pass
            else:
                print("No need to update boot_partition")
        except Exception as e:
            print(f"Warning: could not write currently booted partition to boot_partition in fri3d.sys of NVS: {e}")

        # Wait a few seconds so the user has time to switch off the device in the "boot to retro-go" state
        # This is useful to capture debug logging, as this triggers a re-init of the USB-to-serial.
        self.status_label.set_text("Starting in 3 seconds...")
        await TaskManager.sleep(3)

        try:
            import machine
            machine.reset()
        except Exception as e:
            print(f"Warning: could not restart machine: {e}")
