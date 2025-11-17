import os
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
        icon_path="builtin/res/mipmap-mdpi/default_icon_64x64.png",
        icon_data=None,
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

        self.icon_path = self._find_icon_path()
        #print(f"App constructor got icon_path: {self.icon_path}")
        if self.icon_path:
            self.icon_data = self._load_icon_data(self.icon_path)
        else:
            self.icon_data = None
        self.main_launcher_activity = self._find_main_launcher_activity()

    def __str__(self):
        return f"App({self.name}, version {self.version}, {self.category})"

    def _load_icon_data(self, icon_path):
        #print(f"App _load_icon_data for {icon_path}")
        try:
            f =  open(icon_path, 'rb')
            return f.read()
        except Exception as e:
            #print(f"open {icon_path} got error: {e}")
            pass

    def _check_icon_path(self, tocheck):
        try:
            #print(f"checking {tocheck}")
            st = os.stat(tocheck)
            #print(f"_find_icon_path for {tocheck} found {st}")
            return tocheck
        except Exception as e:
            #print(f"No app icon found in {tocheck}: {e}")
            return None

    def _find_icon_path(self):
        fullpath = "apps/" + self.fullname + "/res/mipmap-mdpi/icon_64x64.png"
        return self._check_icon_path(fullpath) or self._check_icon_path("builtin/" + fullpath)

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

