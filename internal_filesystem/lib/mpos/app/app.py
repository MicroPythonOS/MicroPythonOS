import logging
import ujson

logger = logging.getLogger(__name__)

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
        services=None,
        installed_path=None,
        icon_path="builtin/default_icon_64x64.png",
        icon_data=None,
        blur_hash=None,
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
        self.services = services or []
        self.installed_path = installed_path
        self.blur_hash = blur_hash
        self.main_launcher_activity = self._find_main_launcher_activity()
        if self.fullname != "Unknown":
            self._load_icon_data()

    def __str__(self):
        return f"App({self.name}, version {self.version}, {self.category})"

    def _load_icon_data(self):
        icon_name = "icon_64x64.png"
        flat_paths = [
            f"apps/{self.fullname}/{icon_name}",
            f"builtin/apps/{self.fullname}/{icon_name}",
            f"/builtin/apps/{self.fullname}/{icon_name}",
        ]
        for path in flat_paths:
            self.icon_path, self.icon_data = App._try_load_icon_data(path)
            if self.icon_path:
                return

        # Backward compatibility with the old nested icon layout.
        deprecated_paths = [
            f"apps/{self.fullname}/res/mipmap-mdpi/{icon_name}",
            f"builtin/apps/{self.fullname}/res/mipmap-mdpi/{icon_name}",
            f"/builtin/apps/{self.fullname}/res/mipmap-mdpi/{icon_name}",
        ]
        for path in deprecated_paths:
            self.icon_path, self.icon_data = App._try_load_icon_data(path)
            if self.icon_path:
                logger.warning(
                    "Deprecated icon path: use %s instead of %s",
                    f"apps/{self.fullname}/{icon_name}",
                    path,
                )
                return

        logger.info("Could not find icon for %s", self.fullname)

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
        manifest_path = f"{appdir}/MANIFEST.JSON"
        deprecated_path = f"{appdir}/META-INF/MANIFEST.JSON"
        default = cls(installed_path=appdir)

        try:
            with open(manifest_path, "r") as f:
                data = ujson.load(f)
        except OSError:
            try:
                with open(deprecated_path, "r") as f:
                    data = ujson.load(f)
            except OSError:
                return default
            logger.warning(
                "Deprecated manifest path: use %s instead of %s",
                manifest_path,
                deprecated_path,
            )

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
            services=data.get("services", default.services),
            installed_path=appdir,
        )

    @classmethod
    def _try_load_icon_data(self, icon_path):
        try:
            with open(icon_path, 'rb') as f:
                return icon_path, f.read()
        except Exception:
            return None, None
