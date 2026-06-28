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

        gbc_btn = button_list.add_button(
            None, "Gameboy Color"
        )
        gbc_btn.add_event_cb(
            lambda e: self.launch_retrogo(
                "gbc",
                "GBC",
                "Choose your Gameboy Color ROM:",
                (".gbc", ".gb", ".zip"),
            ),
            lv.EVENT.CLICKED,
            None,
        )

        gw_btn = button_list.add_button(
            None, "Game & Watch"
        )
        gw_btn.add_event_cb(
            lambda e: self.launch_retrogo(
                "gw",
                "GW",
                "Choose your Game & Watch ROM:",
                (".gw",),
            ),
            lv.EVENT.CLICKED,
            None,
        )

        sms_btn = button_list.add_button(
            None, "Sega Master System"
        )
        sms_btn.add_event_cb(
            lambda e: self.launch_retrogo(
                "sms",
                "SMS",
                "Choose your Master System ROM:",
                (".sms", ".sg", ".zip"),
            ),
            lv.EVENT.CLICKED,
            None,
        )

        gg_btn = button_list.add_button(
            None, "Sega Game Gear"
        )
        gg_btn.add_event_cb(
            lambda e: self.launch_retrogo(
                "gg",
                "GG",
                "Choose your Game Gear ROM:",
                (".gg", ".zip"),
            ),
            lv.EVENT.CLICKED,
            None,
        )

        col_btn = button_list.add_button(
            None, "ColecoVision"
        )
        col_btn.add_event_cb(
            lambda e: self.launch_retrogo(
                "col",
                "COL",
                "Choose your ColecoVision ROM:",
                (".col", ".rom", ".zip"),
            ),
            lv.EVENT.CLICKED,
            None,
        )

        pce_btn = button_list.add_button(
            None, "PC Engine"
        )
        pce_btn.add_event_cb(
            lambda e: self.launch_retrogo(
                "pce",
                "PCE",
                "Choose your PC Engine ROM:",
                (".pce", ".zip"),
            ),
            lv.EVENT.CLICKED,
            None,
        )

        lnx_btn = button_list.add_button(
            None, "Atari Lynx"
        )
        lnx_btn.add_event_cb(
            lambda e: self.launch_retrogo(
                "lnx",
                "LNX",
                "Choose your Atari Lynx ROM:",
                (".lnx", ".zip"),
            ),
            lv.EVENT.CLICKED,
            None,
        )

        self.setContentView(screen)

    def launch_retrogo(self, roms_subdir, game_name, title, file_extensions):
        help_text = (
            "• Change audio device and volume by pressing B\n"
            "• To exit, press MENU and choose 'Quit'\n"
        )
        self.startActivity(
            Intent(activity_class=RetroGoLauncher)
            .putExtra("title", title)
            .putExtra("roms_subdir", roms_subdir)
            .putExtra("partition_label", "retro-core")
            .putExtra("boot_name", roms_subdir)
            .putExtra("game_name", game_name)
            .putExtra("file_extensions", file_extensions)
            .putExtra("starting_text", help_text)
        )
