import ujson
import os

class SharedPreferences:
    def __init__(self, appname, filename="config.json", defaults=None):
        """Initialize with appname, filename, and optional defaults for preferences."""
        self.appname = appname
        self.filename = filename
        self.defaults = defaults if defaults is not None else {}
        self.filepath = f"data/{self.appname}/{self.filename}"
        self.data = {}
        self.load()

    def make_folder_structure(self):
        """Create directory structure if it doesn't exist."""
        try:
            os.stat('data')
        except OSError:
            print("Creating data/ directory")
            os.mkdir('data')
        try:
            os.stat(f"data/{self.appname}")
        except OSError:
            print(f"Creating data/{self.appname} directory")
            os.mkdir(f"data/{self.appname}")

    def load(self):
        """Load preferences from the JSON file."""
        try:
            with open(self.filepath, 'r') as f:
                self.data = ujson.load(f)
                print(f"load: Loaded preferences from {self.filepath}: {self.data}")
        except Exception as e:
            print(f"SharedPreferences.load didn't find preferences: {e}")
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
            return self.data[key]
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
            return self.data[key]
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
        """Save preferences to the JSON file."""
        self.make_folder_structure()
        print(f"save_config: Saving preferences to {self.filepath}")
        try:
            with open(self.filepath, 'w') as f:
                ujson.dump(self.data, f)
            print("save_config: Saved")
        except Exception as e:
            print(f"save_config: Got exception {e}")

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
        self.temp_data = preferences.data.copy()

    def put_string(self, key, value):
        """Store a string value."""
        self.temp_data[key] = str(value)
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
        self.preferences.data = filtered_data
        self.preferences.save_config()

    def commit(self):
        """Save changes to the file synchronously."""
        filtered_data = self._filter_defaults(self.temp_data)
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
    print("Simple settings:")
    print("someconfig:", prefs.get_string("someconfig", "default_value"))
    print("othervalue:", prefs.get_int("othervalue", 0))

    print("\nAccess points (dictionary-based):")
    ssids = prefs.get_dict_keys("access_points")
    for ssid in ssids:
        print(f"Access Point SSID: {ssid}")
        print(f"  Password: {prefs.get_dict_item_field('access_points', ssid, 'password', 'N/A')}")
        print(f"  Detail: {prefs.get_dict_item_field('access_points', ssid, 'detail', 'N/A')}")
        print(f"  Numerical Conf: {prefs.get_dict_item_field('access_points', ssid, 'numericalconf', 0)}")
        print(f"  Full config: {prefs.get_dict_item('access_points', ssid)}")

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
    print("\nUpdated access points (dictionary-based):")
    ssids = prefs.get_dict_keys("access_points")
    for ssid in ssids:
        print(f"Access Point SSID: {ssid}: {prefs.get_dict_item('access_points', ssid)}")

    # Demonstrate compatibility with list-based configs
    editor = prefs.edit()
    editor.put_list("somelist", [
        {"a": "ok", "numericalconf": 1111},
        {"a": "not ok", "numericalconf": 2222}
    ])
    editor.apply()

    print("\List-based config:")
    somelist = prefs.get_list("somelist")
    for i, ap in enumerate(somelist):
        print(f"List item {i}:")
        print(f"  a: {prefs.get_list_item('somelist', i, 'a', 'N/A')}")
        print(f"  Full dict: {prefs.get_list_item_dict('somelist', i)}")

if __name__ == '__main__':
    main()
