from mpos import Activity, Intent
from retrogo_launcher import RetroGoLauncher
import lvgl as lv


class RetroCoreLauncher(Activity):
    def onCreate(self):
        screen = lv.obj()
        screen.set_style_pad_all(15, lv.PART.MAIN)

        title_label = lv.label(screen)
        title_label.set_text("Choose your console:")
        title_label.align(lv.ALIGN.TOP_LEFT, 0, 0)

        button_list = lv.list(screen)
        button_list.set_size(lv.pct(100), lv.pct(70))
        button_list.center()

        nes_btn = button_list.add_button(
            None, "NES"
        )
        nes_btn.add_event_cb(
            lambda e: self.launch_retrogo(
                "nes",
                "NES",
                "Choose your NES ROM:",
                (".nes", ".fc", ".fds", ".nsf", ".zip"),
            ),
            lv.EVENT.CLICKED,
            None,
        )

        gb_btn = button_list.add_button(
            None, "Gameboy"
        )
        gb_btn.add_event_cb(
            lambda e: self.launch_retrogo(
                "gb",
                "GB",
                "Choose your Gameboy ROM:",
                (".gb", ".gbc", ".zip"),
            ),
            lv.EVENT.CLICKED,
            None,
        )

        self.setContentView(screen)

    def launch_retrogo(self, roms_subdir, game_name, title, file_extensions):
        self.startActivity(
            Intent(activity_class=RetroGoLauncher)
            .putExtra("title", title)
            .putExtra("roms_subdir", roms_subdir)
            .putExtra("partition_label", "retro-core")
            .putExtra("boot_name", roms_subdir)
            .putExtra("game_name", game_name)
            .putExtra("file_extensions", file_extensions)
        )
