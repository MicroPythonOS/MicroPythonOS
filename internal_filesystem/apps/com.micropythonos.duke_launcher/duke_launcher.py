from mpos import Activity, Intent
from retrogo_launcher import RetroGoLauncher


class DukeLauncher(Activity):

    def onCreate(self):
        help_text = (
            "- To change audio device and volume: MENU - GAME OPTIONS - RETROGO OPTIONS\n"
            "- Hotkey mode: keep START pressed and then:\n"
            "\t- look up/down: Y/B\n"
            "\t- jetpack on: arrow down\n"
            "\t- joystick left/right to scroll, arrow up to choose\n"
            "- Shoot: A, Jump: B, Weapon: X, Crouch: Y, Use: START\n"
            "- Autoaim is on so no no need to look up and down"
        )
        self.startActivity(
            Intent(activity_class=RetroGoLauncher)
            .putExtra("title", "Choose your DUKE NUKEM 3D:")
            .putExtra("roms_subdir", "duke3d")
            .putExtra("partition_label", "duke3d-go")
            .putExtra("boot_name", "duke3d")
            .putExtra("game_name", "Duke Nukem 3D")
            .putExtra("file_extensions", (".grp", ".zip"))
            .putExtra("starting_text", help_text)
        )
