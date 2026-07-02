from mpos import Activity, Intent
from retrogo_launcher import RetroGoLauncher


class DoomLauncher(Activity):

    def onCreate(self):
        self.startActivity(
            Intent(activity_class=RetroGoLauncher)
            .putExtra("title", "Choose your DOOM:")
            .putExtra("roms_subdir", "doom")
            .putExtra("partition_label", "prboom-go")
            .putExtra("boot_name", "doom")
            .putExtra("game_name", "Doom")
            .putExtra("file_extensions", (".wad", ".zip"))
        )
