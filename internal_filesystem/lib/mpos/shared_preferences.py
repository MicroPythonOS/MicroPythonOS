import logging
import ujson
import os

logger = logging.getLogger(__name__)

_PREFS_DIR = "data/prefs"
_LEGACY_PREFS_DIR = "data"


class SharedPreferences:
    # Track appnames already checked for legacy migration this process.
    _migrated_appnames = set()

    def __init__(self, appname, filename="config.json", defaults=None):
        """Initialize with appname, filename, and optional defaults for preferences."""
        self.appname = appname
        self.filename = filename
        self.defaults = defaults if defaults is not None else {}
        self.appdir = f"{_PREFS_DIR}/{self.appname}"
        self.filepath = f"{self.appdir}/{self.filename}"
        self.data = {}
        self.load()

    @staticmethod
    def _path_exists(path):
        try:
            os.stat(path)
            return True
        except OSError:
            return False

    def _file_exists(self):
        return self._path_exists(self.filepath)

    @staticmethod
    def _remove_if_exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            return False

    @staticmethod
    def _remove_dir_if_empty(path):
        try:
            os.rmdir(path)
            return True
        except OSError:
            return False

    def _ensure_prefs_dir(self):
        """Create data/ and data/prefs/ directories if they don't exist."""
        if not self._path_exists("data"):
            if __debug__: logger.debug("Creating data/ directory")
            os.mkdir("data")
        if not self._path_exists(_PREFS_DIR):
            if __debug__: logger.debug("Creating %s directory", _PREFS_DIR)
            os.mkdir(_PREFS_DIR)

    def make_folder_structure(self):
        """Create directory structure if it doesn't exist."""
        self._ensure_prefs_dir()
        if not self._path_exists(self.appdir):
            if __debug__: logger.debug("Creating %s directory", self.appdir)
            os.mkdir(self.appdir)

    def _remove_empty_preference_dirs(self):
        """Remove app/data directories if they became empty."""
        self._remove_dir_if_empty(self.appdir)
        self._remove_dir_if_empty(_PREFS_DIR)
        self._remove_dir_if_empty("data")

    def _load_file(self, path):
        """Load preferences from the given JSON file path."""
        try:
            with open(path, 'r') as f:
                self.data = ujson.load(f)
                # Deliberately log only the filepath and key count, NOT the
                # values. Prefs often hold secrets (WiFi passwords in
                # access_points, wallet API keys / NWC secrets / xpubs in
                # third-party apps, etc.) — printing self.data leaked those
                # to serial/REPL every time any app loaded its prefs. An
                # app that wants rich debug output can opt in by logging
                # selected keys itself.
                if __debug__: logger.debug("load: Loaded preferences from %s (%s keys)", path, len(self.data))
        except Exception as e:
            if __debug__: logger.debug("SharedPreferences.load didn't find preferences: %s", e)
            self.data = {}

    def _migrate_legacy(self):
        """Move preferences from the legacy path to the new path, once per appname."""
        legacy_appdir = f"{_LEGACY_PREFS_DIR}/{self.appname}"
        legacy_filepath = f"{legacy_appdir}/{self.filename}"

        if not self._path_exists(legacy_filepath):
            return

        if __debug__:
            logger.debug("Migrating legacy preferences for %s from %s to %s", self.appname, legacy_filepath, self.filepath)

        self._ensure_prefs_dir()

        # Fast path: move the whole legacy app directory in one shot.
        if not self._path_exists(self.appdir):
            try:
                os.rename(legacy_appdir, self.appdir)
                self._remove_empty_legacy_dirs()
                return
            except OSError:
                # Target may already exist or rename not supported; fall back to file move.
                pass

        # Slow path: ensure appdir exists and move only this file.
        self.make_folder_structure()
        try:
            os.rename(legacy_filepath, self.filepath)
            self._remove_empty_legacy_dirs()
        except OSError:
            pass

    def _remove_empty_legacy_dirs(self):
        """Remove legacy app/data directories if they became empty."""
        self._remove_dir_if_empty(f"{_LEGACY_PREFS_DIR}/{self.appname}")
        self._remove_dir_if_empty(_LEGACY_PREFS_DIR)

    def load(self):
        """Load preferences from the JSON file, migrating legacy data if needed."""
        if self._path_exists(self.filepath):
            self._load_file(self.filepath)
            return

        if self.appname not in SharedPreferences._migrated_appnames:
            SharedPreferences._migrated_appnames.add(self.appname)
            self._migrate_legacy()

        if self._path_exists(self.filepath):
            self._load_file(self.filepath)
        else:
            if __debug__: logger.debug("SharedPreferences.load didn't find preferences for %s", self.appname)
            self.data = {}

    def get_string(self, key, default=None):
        """Retrieve a string value for the given key, with a default if not found."""
        to_return = self.data.get(key)
        if to_return is None:
            # Method default takes precedence
            if default is not None:
                to_return = default
            # Fall back to constructor default
            elif key in self.defaults:
                to_return = self.defaults[key]
        return to_return

    def get_int(self, key, default=0):
        """Retrieve an integer value for the given key, with a default if not found."""
        if key in self.data:
            try:
                return int(self.data[key])
            except (TypeError, ValueError):
                return default
        # Key not in stored data, check defaults
        # Method default takes precedence if explicitly provided (not the hardcoded 0)
        # Otherwise use constructor default if exists
        if default != 0:
            return default
        if key in self.defaults:
            try:
                return int(self.defaults[key])
            except (TypeError, ValueError):
                return 0
        return 0

    def get_bool(self, key, default=False):
        """Retrieve a boolean value for the given key, with a default if not found."""
        if key in self.data:
            try:
                return bool(self.data[key])
            except (TypeError, ValueError):
                return default
        # Key not in stored data, check defaults
        # Method default takes precedence if explicitly provided (not the hardcoded False)
        # Otherwise use constructor default if exists
        if default != False:
            return default
        if key in self.defaults:
            try:
                return bool(self.defaults[key])
            except (TypeError, ValueError):
                return False
        return False

    def get_list(self, key, default=None):
        """Retrieve a list for the given key, with a default if not found."""
        if key in self.data:
            return list(self.data[key])  # return a copy — callers must not mutate prefs.data directly
        # Key not in stored data, check defaults
        # Method default takes precedence if provided
        if default is not None:
            return default
        # Fall back to constructor default
        if key in self.defaults:
            return self.defaults[key]
        # Return empty list as hardcoded fallback
        return []

    def get_dict(self, key, default=None):
        """Retrieve a dictionary for the given key, with a default if not found."""
        if key in self.data:
            return dict(self.data[key])  # return a copy — callers must not mutate prefs.data directly
        # Key not in stored data, check defaults
        # Method default takes precedence if provided
        if default is not None:
            return default
        # Fall back to constructor default
        if key in self.defaults:
            return self.defaults[key]
        # Return empty dict as hardcoded fallback
        return {}

    def edit(self):
        """Return an Editor object to modify preferences."""
        return Editor(self)

    def save_config(self):
        """Save preferences to the JSON file, pruning empty files/dirs."""
        if not self.data:
            removed_file = self._remove_if_exists(self.filepath)
            if removed_file:
                if __debug__: logger.debug("save_config: Removed empty preferences file %s", self.filepath)
            self._remove_empty_preference_dirs()
            return

        self.make_folder_structure()
        if __debug__: logger.debug("save_config: Saving preferences to %s", self.filepath)
        try:
            with open(self.filepath, 'w') as f:
                ujson.dump(self.data, f)
            if __debug__: logger.debug("save_config: Saved")
        except Exception as e:
            logger.error("save_config: Got exception %s", e)

    # Methods for list-based structures
    def get_list_item(self, list_key, index, item_key, default=None):
        """Retrieve a specific item's value from a list of dictionaries."""
        try:
            return self.data.get(list_key, [])[index].get(item_key, default)
        except (IndexError, KeyError, TypeError):
            return default

    def get_list_item_dict(self, list_key, index, default=None):
        """Retrieve an entire dictionary from a list at the specified index."""
        try:
            return self.data.get(list_key, [])[index]
        except (IndexError, TypeError):
            return default if default is not None else {}

    # Generic methods for dictionary-based structures
    def get_dict_item_field(self, dict_key, item_key, field, default=None):
        """Retrieve a specific field for an item in a dictionary by item_key."""
        try:
            return self.data.get(dict_key, {}).get(item_key, {}).get(field, default)
        except (KeyError, TypeError):
            return default

    def get_dict_item(self, dict_key, item_key, default=None):
        """Retrieve the entire configuration for an item in a dictionary by item_key."""
        try:
            return self.data.get(dict_key, {}).get(item_key, default if default is not None else {})
        except (KeyError, TypeError):
            return default if default is not None else {}

    def get_dict_keys(self, dict_key):
        """Retrieve a list of all keys in a dictionary at dict_key."""
        try:
            return list(self.data.get(dict_key, {}).keys())
        except (KeyError, TypeError):
            return []

class Editor:
    def __init__(self, preferences):
        """Initialize Editor with a reference to SharedPreferences."""
        self.preferences = preferences
        # Use a deep copy so nested edits do not mutate preferences.data before
        # commit/apply no-op checks run.
        self.temp_data = ujson.loads(ujson.dumps(preferences.data))

    def put_string(self, key, value):
        """Store a string value."""
        self.temp_data[key] = None if value is None else str(value)
        return self

    def put_int(self, key, value):
        """Store an integer value."""
        self.temp_data[key] = int(value)
        return self

    def put_bool(self, key, value):
        """Store a boolean value."""
        self.temp_data[key] = bool(value)
        return self

    def put_list(self, key, value):
        """Store a list value."""
        if isinstance(value, list):
            self.temp_data[key] = value
        return self

    def put_dict(self, key, value):
        """Store a dictionary value."""
        if isinstance(value, dict):
            self.temp_data[key] = value
        return self

    def append_to_list(self, list_key, item):
        """Append a dictionary to a list in the preferences."""
        if list_key not in self.temp_data:
            self.temp_data[list_key] = []
        if isinstance(item, dict):
            self.temp_data[list_key].append(item)
        return self

    def update_list_item(self, list_key, index, item):
        """Update a dictionary at a specific index in a list."""
        try:
            if list_key in self.temp_data and isinstance(self.temp_data[list_key], list):
                if index < len(self.temp_data[list_key]) and isinstance(item, dict):
                    self.temp_data[list_key][index] = item
        except (IndexError, TypeError):
            pass
        return self

    def remove_from_list(self, list_key, index):
        """Remove an item from a list at the specified index."""
        try:
            if list_key in self.temp_data and isinstance(self.temp_data[list_key], list):
                if index < len(self.temp_data[list_key]):
                    self.temp_data[list_key].pop(index)
        except (IndexError, TypeError):
            pass
        return self

    # Generic methods for dictionary-based structures
    def put_dict_item(self, dict_key, item_key, config):
        """Add or update an item in a dictionary by item_key."""
        if dict_key not in self.temp_data:
            self.temp_data[dict_key] = {}
        if isinstance(config, dict):
            self.temp_data[dict_key][item_key] = config
        return self

    def remove_dict_item(self, dict_key, item_key):
        """Remove an item from a dictionary by item_key."""
        try:
            if dict_key in self.temp_data and isinstance(self.temp_data[dict_key], dict):
                self.temp_data[dict_key].pop(item_key, None)
        except (KeyError, TypeError):
            pass
        return self

    def remove_all(self):
        self.temp_data = {}
        return self

    def _filter_defaults(self, data):
        """Remove keys from data that match constructor defaults."""
        if not self.preferences.defaults:
            return data

        filtered = {}
        for key, value in data.items():
            if key in self.preferences.defaults:
                if value != self.preferences.defaults[key]:
                    filtered[key] = value
                # else: skip saving, matches default
            else:
                filtered[key] = value  # No default, always save
        return filtered

    def apply(self):
        """Save changes to the file asynchronously (emulated)."""
        filtered_data = self._filter_defaults(self.temp_data)

        # No-op write guard: if filtered data did not change and there is no
        # legacy empty file to clean up, avoid touching the filesystem.
        if filtered_data == self.preferences.data:
            if filtered_data or not self.preferences._file_exists():
                if __debug__: logger.debug("save_config: Skipping no-op apply")
                self.preferences.data = filtered_data
                return

        self.preferences.data = filtered_data
        self.preferences.save_config()

    def commit(self):
        """Save changes to the file synchronously."""
        filtered_data = self._filter_defaults(self.temp_data)

        # No-op write guard: if filtered data did not change and there is no
        # legacy empty file to clean up, avoid touching the filesystem.
        if filtered_data == self.preferences.data:
            if filtered_data or not self.preferences._file_exists():
                if __debug__: logger.debug("save_config: Skipping no-op commit")
                self.preferences.data = filtered_data
                return True

        self.preferences.data = filtered_data
        self.preferences.save_config()
        return True

# Example usage with access_points as a dictionary
def main():
    # Initialize SharedPreferences
    prefs = SharedPreferences("com.example.test_shared_prefs")

    # Save some simple settings and a dictionary-based access_points
    editor = prefs.edit()
    editor.put_string("someconfig", "somevalue")
    editor.put_int("othervalue", 54321)
    editor.put_dict("access_points", {
        "example_ssid1": {"password": "examplepass1", "detail": "yes please", "numericalconf": 1234},
        "example_ssid2": {"password": "examplepass2", "detail": "no please", "numericalconf": 9875}
    })
    editor.apply()

    # Read back the settings
    if __debug__: logger.debug("Simple settings:")
    if __debug__: logger.debug("someconfig: %s", prefs.get_string("someconfig", "default_value"))
    if __debug__: logger.debug("othervalue: %s", prefs.get_int("othervalue", 0))

    if __debug__: logger.debug("Access points (dictionary-based):")
    ssids = prefs.get_dict_keys("access_points")
    for ssid in ssids:
        if __debug__: logger.debug("Access Point SSID: %s", ssid)
        if __debug__: logger.debug("  Password: %s", prefs.get_dict_item_field('access_points', ssid, 'password', 'N/A'))
        if __debug__: logger.debug("  Detail: %s", prefs.get_dict_item_field('access_points', ssid, 'detail', 'N/A'))
        if __debug__: logger.debug("  Numerical Conf: %s", prefs.get_dict_item_field('access_points', ssid, 'numericalconf', 0))
        if __debug__: logger.debug("  Full config: %s", prefs.get_dict_item('access_points', ssid))

    # Add a new access point
    editor = prefs.edit()
    editor.put_dict_item("access_points", "example_ssid3", {
        "password": "examplepass3",
        "detail": "maybe",
        "numericalconf": 5555
    })
    editor.commit()

    # Update an existing access point
    editor = prefs.edit()
    editor.put_dict_item("access_points", "example_ssid1", {
        "password": "newpass1",
        "detail": "updated please",
        "numericalconf": 4321
    })
    editor.commit()

    # Remove an access point
    editor = prefs.edit()
    editor.remove_dict_item("access_points", "example_ssid2")
    editor.commit()

    # Read updated access points
    if __debug__: logger.debug("Updated access points (dictionary-based):")
    ssids = prefs.get_dict_keys("access_points")
    for ssid in ssids:
        if __debug__: logger.debug("Access Point SSID: %s: %s", ssid, prefs.get_dict_item('access_points', ssid))

    # Demonstrate compatibility with list-based configs
    editor = prefs.edit()
    editor.put_list("somelist", [
        {"a": "ok", "numericalconf": 1111},
        {"a": "not ok", "numericalconf": 2222}
    ])
    editor.apply()

    if __debug__: logger.debug("List-based config:")
    somelist = prefs.get_list("somelist")
    for i, ap in enumerate(somelist):
        if __debug__: logger.debug("List item %s:", i)
        if __debug__: logger.debug("  a: %s", prefs.get_list_item('somelist', i, 'a', 'N/A'))
        if __debug__: logger.debug("  Full dict: %s", prefs.get_list_item_dict('somelist', i))

if __name__ == '__main__':
    main()
