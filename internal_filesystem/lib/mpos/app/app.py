import ujson
from ..activity_navigator import ActivityNavigator

class App:
    def __init__(
        self,
        name="Unknown",
        publisher="Unknown",
        short_description="",
        long_description="",
        icon_url="",
        download_url="",
        fullname="Unknown",
        version="0.0.0",
        category="",
        activities=None,
        installed_path=None,
    ):
        self.name = name
        self.publisher = publisher
        self.short_description = short_description
        self.long_description = long_description
        self.icon_url = icon_url
        self.download_url = download_url
        self.fullname = fullname
        self.version = version
        self.category = category
        self.activities = activities or []
        self.installed_path = installed_path

        self.image = None
        self.image_dsc = None
        self.main_launcher_activity = self._find_main_launcher_activity()

    def __str__(self):
        return f"App({self.name}, v{self.version}, {self.category})"

    def _find_main_launcher_activity(self):
        for act in self.activities:
            if not act.get("entrypoint") or not act.get("classname"):
                continue
            for f in act.get("intent_filters", []):
                if f.get("action") == "main" and f.get("category") == "launcher":
                    return act
        return None

    def is_valid_launcher(self):
        return self.category == "launcher" and self.main_launcher_activity

    @classmethod
    def from_manifest(cls, appdir):
        manifest_path = f"{appdir}/META-INF/MANIFEST.JSON"
        default = cls(installed_path=appdir)
        try:
            with open(manifest_path, "r") as f:
                data = ujson.load(f)
        except OSError:
            return default

        return cls(
            name=data.get("name", default.name),
            publisher=data.get("publisher", default.publisher),
            short_description=data.get("short_description", default.short_description),
            long_description=data.get("long_description", default.long_description),
            icon_url=data.get("icon_url", default.icon_url),
            download_url=data.get("download_url", default.download_url),
            fullname=data.get("fullname", default.fullname),
            version=data.get("version", default.version),
            category=data.get("category", default.category),
            activities=data.get("activities", default.activities),
            installed_path=appdir,
        )

