import unittest
import os
from mpos.config import SharedPreferences, Editor


class TestSharedPreferences(unittest.TestCase):
    """Test suite for SharedPreferences configuration storage."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.test_app_name = "com.test.unittest"
        self.test_dir = f"data/{self.test_app_name}"
        self.test_file = f"{self.test_dir}/config.json"
        # Clean up any existing test data
        self._cleanup()

    def tearDown(self):
        """Clean up test fixtures after each test method."""
        self._cleanup()

    def _cleanup(self):
        """Remove test data directory if it exists."""
        try:
            # Use os.stat() instead of os.path.exists() for MicroPython compatibility
            try:
                os.stat(self.test_file)
                os.remove(self.test_file)
            except OSError:
                pass  # File doesn't exist, that's fine

            try:
                os.stat(self.test_dir)
                os.rmdir(self.test_dir)
            except OSError:
                pass  # Directory doesn't exist, that's fine

            try:
                os.stat("data")
                # Try to remove data directory, but it might have other contents
                try:
                    os.rmdir("data")
                except OSError:
                    # Directory not empty, that's okay
                    pass
            except OSError:
                pass  # Directory doesn't exist, that's fine
        except Exception as e:
            # Cleanup failure is not critical for tests
            print(f"Cleanup warning: {e}")

    # ============================================================
    # Basic String Operations
    # ============================================================

    def test_put_get_string(self):
        """Test storing and retrieving a string value."""
        prefs = SharedPreferences(self.test_app_name)
        editor = prefs.edit()
        editor.put_string("username", "testuser")
        editor.commit()

        # Reload to verify persistence
        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_string("username"), "testuser")

    def test_get_string_default(self):
        """Test getting a string with default value when key doesn't exist."""
        prefs = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs.get_string("nonexistent", "default"), "default")
        self.assertIsNone(prefs.get_string("nonexistent"))

    def test_put_string_overwrites(self):
        """Test that putting a string overwrites existing value."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_string("key", "value1").commit()
        prefs.edit().put_string("key", "value2").commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_string("key"), "value2")

    # ============================================================
    # Integer Operations
    # ============================================================

    def test_put_get_int(self):
        """Test storing and retrieving an integer value."""
        prefs = SharedPreferences(self.test_app_name)
        editor = prefs.edit()
        editor.put_int("count", 42)
        editor.commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_int("count"), 42)

    def test_get_int_default(self):
        """Test getting an integer with default value when key doesn't exist."""
        prefs = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs.get_int("nonexistent", 100), 100)
        self.assertEqual(prefs.get_int("nonexistent"), 0)

    def test_get_int_invalid_type(self):
        """Test getting an integer when stored value is invalid."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_string("invalid", "not_a_number").commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_int("invalid", 99), 99)

    # ============================================================
    # Boolean Operations
    # ============================================================

    def test_put_get_bool(self):
        """Test storing and retrieving boolean values."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_bool("enabled", True).commit()
        prefs.edit().put_bool("disabled", False).commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertTrue(prefs2.get_bool("enabled"))
        self.assertFalse(prefs2.get_bool("disabled"))

    def test_get_bool_default(self):
        """Test getting a boolean with default value when key doesn't exist."""
        prefs = SharedPreferences(self.test_app_name)
        self.assertTrue(prefs.get_bool("nonexistent", True))
        self.assertFalse(prefs.get_bool("nonexistent", False))
        self.assertFalse(prefs.get_bool("nonexistent"))

    # ============================================================
    # List Operations
    # ============================================================

    def test_put_get_list(self):
        """Test storing and retrieving a list."""
        prefs = SharedPreferences(self.test_app_name)
        test_list = [1, 2, 3, "four"]
        prefs.edit().put_list("mylist", test_list).commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_list("mylist"), test_list)

    def test_get_list_default(self):
        """Test getting a list with default value when key doesn't exist."""
        prefs = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs.get_list("nonexistent"), [])
        self.assertEqual(prefs.get_list("nonexistent", ["a", "b"]), ["a", "b"])

    def test_append_to_list(self):
        """Test appending items to a list."""
        prefs = SharedPreferences(self.test_app_name)
        editor = prefs.edit()
        editor.append_to_list("items", {"id": 1, "name": "first"})
        editor.append_to_list("items", {"id": 2, "name": "second"})
        editor.commit()

        prefs2 = SharedPreferences(self.test_app_name)
        items = prefs2.get_list("items")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], 1)
        self.assertEqual(items[1]["name"], "second")

    def test_update_list_item(self):
        """Test updating an item in a list."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_list("items", [{"a": 1}, {"b": 2}]).commit()

        prefs.edit().update_list_item("items", 1, {"b": 99}).commit()

        prefs2 = SharedPreferences(self.test_app_name)
        items = prefs2.get_list("items")
        self.assertEqual(items[1]["b"], 99)

    def test_remove_from_list(self):
        """Test removing an item from a list."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_list("items", [{"a": 1}, {"b": 2}, {"c": 3}]).commit()

        prefs.edit().remove_from_list("items", 1).commit()

        prefs2 = SharedPreferences(self.test_app_name)
        items = prefs2.get_list("items")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["a"], 1)
        self.assertEqual(items[1]["c"], 3)

    def test_get_list_item(self):
        """Test getting a specific field from a list item."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_list("users", [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25}
        ]).commit()

        self.assertEqual(prefs.get_list_item("users", 0, "name"), "Alice")
        self.assertEqual(prefs.get_list_item("users", 1, "age"), 25)
        self.assertIsNone(prefs.get_list_item("users", 99, "name"))
        self.assertEqual(prefs.get_list_item("users", 99, "name", "default"), "default")

    def test_get_list_item_dict(self):
        """Test getting an entire dictionary from a list."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_list("configs", [{"key": "value"}]).commit()

        item = prefs.get_list_item_dict("configs", 0)
        self.assertEqual(item["key"], "value")
        self.assertEqual(prefs.get_list_item_dict("configs", 99), {})

    # ============================================================
    # Dictionary Operations
    # ============================================================

    def test_put_get_dict(self):
        """Test storing and retrieving a dictionary."""
        prefs = SharedPreferences(self.test_app_name)
        test_dict = {"key1": "value1", "key2": 42}
        prefs.edit().put_dict("mydict", test_dict).commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_dict("mydict"), test_dict)

    def test_get_dict_default(self):
        """Test getting a dict with default value when key doesn't exist."""
        prefs = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs.get_dict("nonexistent"), {})
        self.assertEqual(prefs.get_dict("nonexistent", {"default": True}), {"default": True})

    def test_put_dict_item(self):
        """Test adding items to a dictionary."""
        prefs = SharedPreferences(self.test_app_name)
        editor = prefs.edit()
        editor.put_dict_item("wifi_aps", "HomeNetwork", {"password": "secret123", "priority": 1})
        editor.put_dict_item("wifi_aps", "WorkNetwork", {"password": "work456", "priority": 2})
        editor.commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_dict_item("wifi_aps", "HomeNetwork")["password"], "secret123")
        self.assertEqual(prefs2.get_dict_item("wifi_aps", "WorkNetwork")["priority"], 2)

    def test_remove_dict_item(self):
        """Test removing an item from a dictionary."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_dict("items", {"a": 1, "b": 2, "c": 3}).commit()

        prefs.edit().remove_dict_item("items", "b").commit()

        prefs2 = SharedPreferences(self.test_app_name)
        items = prefs2.get_dict("items")
        self.assertEqual(len(items), 2)
        self.assertIn("a", items)
        self.assertIn("c", items)
        self.assertFalse("b" in items)  # Use 'in' operator instead of assertNotIn

    def test_get_dict_item(self):
        """Test getting a specific item from a dictionary."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_dict("settings", {
            "theme": {"color": "blue", "size": 14},
            "audio": {"volume": 80}
        }).commit()

        theme = prefs.get_dict_item("settings", "theme")
        self.assertEqual(theme["color"], "blue")
        self.assertEqual(prefs.get_dict_item("settings", "nonexistent"), {})

    def test_get_dict_item_field(self):
        """Test getting a specific field from a dict item."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_dict("networks", {
            "ssid1": {"password": "pass1", "signal": 100},
            "ssid2": {"password": "pass2", "signal": 50}
        }).commit()

        self.assertEqual(prefs.get_dict_item_field("networks", "ssid1", "password"), "pass1")
        self.assertEqual(prefs.get_dict_item_field("networks", "ssid2", "signal"), 50)
        self.assertIsNone(prefs.get_dict_item_field("networks", "ssid99", "password"))
        self.assertEqual(prefs.get_dict_item_field("networks", "ssid1", "missing", "def"), "def")

    def test_get_dict_keys(self):
        """Test getting all keys from a dictionary."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_dict("items", {"a": 1, "b": 2, "c": 3}).commit()

        keys = prefs.get_dict_keys("items")
        self.assertEqual(len(keys), 3)
        self.assertIn("a", keys)
        self.assertIn("b", keys)
        self.assertIn("c", keys)

    def test_get_dict_keys_nonexistent(self):
        """Test getting keys from a nonexistent dictionary."""
        prefs = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs.get_dict_keys("nonexistent"), [])

    # ============================================================
    # Editor Operations
    # ============================================================

    def test_editor_chaining(self):
        """Test that editor methods can be chained."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit()\
            .put_string("name", "test")\
            .put_int("count", 5)\
            .put_bool("enabled", True)\
            .commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_string("name"), "test")
        self.assertEqual(prefs2.get_int("count"), 5)
        self.assertTrue(prefs2.get_bool("enabled"))

    def test_editor_apply_vs_commit(self):
        """Test that both apply and commit save data."""
        prefs = SharedPreferences(self.test_app_name)

        # Test apply
        prefs.edit().put_string("key1", "apply_test").apply()
        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_string("key1"), "apply_test")

        # Test commit
        prefs.edit().put_string("key2", "commit_test").commit()
        prefs3 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs3.get_string("key2"), "commit_test")

    def test_editor_without_commit_doesnt_save(self):
        """Test that changes without commit/apply are not persisted."""
        prefs = SharedPreferences(self.test_app_name)
        editor = prefs.edit()
        editor.put_string("unsaved", "value")
        # Don't call commit() or apply()

        # Reload and verify data wasn't saved
        prefs2 = SharedPreferences(self.test_app_name)
        self.assertIsNone(prefs2.get_string("unsaved"))

    def test_multiple_edits(self):
        """Test multiple sequential edit operations."""
        prefs = SharedPreferences(self.test_app_name)

        prefs.edit().put_string("step", "1").commit()
        prefs.edit().put_string("step", "2").commit()
        prefs.edit().put_string("step", "3").commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_string("step"), "3")

    # ============================================================
    # File Persistence
    # ============================================================

    def test_directory_creation(self):
        """Test that directory structure is created automatically."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_string("test", "value").commit()

        # Use os.stat() instead of os.path.exists() for MicroPython
        try:
            os.stat("data")
            data_exists = True
        except OSError:
            data_exists = False
        self.assertTrue(data_exists)

        try:
            os.stat(self.test_dir)
            dir_exists = True
        except OSError:
            dir_exists = False
        self.assertTrue(dir_exists)

        try:
            os.stat(self.test_file)
            file_exists = True
        except OSError:
            file_exists = False
        self.assertTrue(file_exists)

    def test_custom_filename(self):
        """Test using a custom filename for preferences."""
        prefs = SharedPreferences(self.test_app_name, "custom.json")
        prefs.edit().put_string("custom", "data").commit()

        custom_file = f"{self.test_dir}/custom.json"
        # Use os.stat() instead of os.path.exists() for MicroPython
        try:
            os.stat(custom_file)
            file_exists = True
        except OSError:
            file_exists = False
        self.assertTrue(file_exists)

        prefs2 = SharedPreferences(self.test_app_name, "custom.json")
        self.assertEqual(prefs2.get_string("custom"), "data")

    def test_load_existing_file(self):
        """Test loading from an existing preferences file."""
        # Create initial prefs
        prefs1 = SharedPreferences(self.test_app_name)
        prefs1.edit().put_string("existing", "data").commit()

        # Load in a new instance
        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_string("existing"), "data")

    # ============================================================
    # Edge Cases and Error Handling
    # ============================================================

    def test_empty_string_values(self):
        """Test storing and retrieving empty strings."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_string("empty", "").commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_string("empty"), "")

    def test_zero_values(self):
        """Test storing and retrieving zero values."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_int("zero", 0).put_bool("false", False).commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_int("zero"), 0)
        self.assertFalse(prefs2.get_bool("false"))

    def test_none_values(self):
        """Test handling None values gracefully."""
        prefs = SharedPreferences(self.test_app_name)
        # Getting a nonexistent key should return None or default
        self.assertIsNone(prefs.get_string("nonexistent"))

    def test_special_characters_in_keys(self):
        """Test keys with special characters."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit()\
            .put_string("key.with.dots", "value1")\
            .put_string("key_with_underscores", "value2")\
            .put_string("key-with-dashes", "value3")\
            .commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_string("key.with.dots"), "value1")
        self.assertEqual(prefs2.get_string("key_with_underscores"), "value2")
        self.assertEqual(prefs2.get_string("key-with-dashes"), "value3")

    def test_unicode_values(self):
        """Test storing and retrieving Unicode strings."""
        prefs = SharedPreferences(self.test_app_name)
        prefs.edit().put_string("unicode", "Hello 世界 🌍").commit()

        prefs2 = SharedPreferences(self.test_app_name)
        self.assertEqual(prefs2.get_string("unicode"), "Hello 世界 🌍")

    def test_large_nested_structure(self):
        """Test storing a complex nested data structure."""
        prefs = SharedPreferences(self.test_app_name)
        complex_data = {
            "users": {
                "alice": {"age": 30, "roles": ["admin", "user"]},
                "bob": {"age": 25, "roles": ["user"]}
            },
            "settings": {
                "theme": "dark",
                "notifications": True,
                "limits": [10, 20, 30]
            }
        }
        prefs.edit().put_dict("app_data", complex_data).commit()

        prefs2 = SharedPreferences(self.test_app_name)
        loaded = prefs2.get_dict("app_data")
        self.assertEqual(loaded["users"]["alice"]["age"], 30)
        self.assertEqual(loaded["settings"]["theme"], "dark")
        self.assertEqual(loaded["settings"]["limits"][2], 30)


