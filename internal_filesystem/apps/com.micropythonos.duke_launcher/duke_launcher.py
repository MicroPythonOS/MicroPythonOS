from mpos import Activity, Intent
from retrogo_launcher import RetroGoLauncher


class DukeLauncher(Activity):

    def onCreate(self):
        self.startActivity(
            Intent(activity_class=RetroGoLauncher)
            .putExtra("title", "Choose your DUKE NUKEM 3D:")
            .putExtra("roms_subdir", "duke3d")
            .putExtra("partition_label", "duke3d-go")
            .putExtra("boot_name", "duke3d")
            .putExtra("game_name", "Duke Nukem 3D")
            .putExtra("file_extensions", (".grp", ".zip"))
        )
