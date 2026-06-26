from mpos import Activity, Intent
from retrogo_launcher import RetroGoLauncher


class DukeLauncher(Activity):

    def onCreate(self):
        help_text = (
            "- Shoot: A, Jump: B, Weapon: X, Crouch: Y, Use: START\n"
            "- Autoaim is on (no need to look up or down)"
            "- Changing audio device and volume: MENU - GAME OPTIONS - RETROGO OPTIONS\n"
            "- Hotkey: long-press START\n"
            "    + look up/down: Y/B\n"
            "    + jetpack on: arrow down\n"
            "    + joystick left/right to scroll, arrow up to choose\n"
        )
        self.startActivity(
            Intent(activity_class=RetroGoLauncher)
            .putExtra("title", "Choose your DUKE NUKEM 3D:")
            .putExtra("roms_subdir", "duke3d")
            .putExtra("partition_label", "duke3d-go")
            .putExtra("boot_name", "duke3d")
            .putExtra("game_name", "Duke Nukem 3D")
            .putExtra("file_extensions", (".grp", ".zip"))
            .putExtra("starting_title", "Hints:")
            .putExtra("starting_text", help_text)
        )
