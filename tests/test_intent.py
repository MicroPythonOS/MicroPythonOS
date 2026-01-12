import unittest
from mpos import Intent


class TestIntent(unittest.TestCase):
    """Test suite for Intent class."""

    # ============================================================
    # Intent Construction
    # ============================================================

    def test_empty_intent(self):
        """Test creating an empty intent."""
        intent = Intent()
        self.assertIsNone(intent.activity_class)
        self.assertIsNone(intent.action)
        self.assertIsNone(intent.data)
        self.assertEqual(intent.extras, {})
        self.assertEqual(intent.flags, {})

    def test_intent_with_activity_class(self):
        """Test creating an intent with an explicit activity class."""
        class MockActivity:
            pass

        intent = Intent(activity_class=MockActivity)
        self.assertEqual(intent.activity_class, MockActivity)
        self.assertIsNone(intent.action)

    def test_intent_with_action(self):
        """Test creating an intent with an action."""
        intent = Intent(action="view")
        self.assertEqual(intent.action, "view")
        self.assertIsNone(intent.activity_class)

    def test_intent_with_data(self):
        """Test creating an intent with data."""
        intent = Intent(data="https://example.com")
        self.assertEqual(intent.data, "https://example.com")

    def test_intent_with_extras(self):
        """Test creating an intent with extras dictionary."""
        extras = {"user_id": 123, "username": "alice"}
        intent = Intent(extras=extras)
        self.assertEqual(intent.extras, extras)

    def test_intent_with_all_parameters(self):
        """Test creating an intent with all parameters."""
        class MockActivity:
            pass

        extras = {"key": "value"}
        intent = Intent(
            activity_class=MockActivity,
            action="share",
            data="some_data",
            extras=extras
        )

        self.assertEqual(intent.activity_class, MockActivity)
        self.assertEqual(intent.action, "share")
        self.assertEqual(intent.data, "some_data")
        self.assertEqual(intent.extras, extras)

    # ============================================================
    # Extras Operations
    # ============================================================

    def test_put_extra_single(self):
        """Test adding a single extra to an intent."""
        intent = Intent()
        intent.putExtra("key", "value")
        self.assertEqual(intent.extras["key"], "value")

    def test_put_extra_multiple(self):
        """Test adding multiple extras to an intent."""
        intent = Intent()
        intent.putExtra("key1", "value1")
        intent.putExtra("key2", 42)
        intent.putExtra("key3", True)

        self.assertEqual(intent.extras["key1"], "value1")
        self.assertEqual(intent.extras["key2"], 42)
        self.assertTrue(intent.extras["key3"])

    def test_put_extra_chaining(self):
        """Test that putExtra returns self for method chaining."""
        intent = Intent()
        result = intent.putExtra("key", "value")
        self.assertEqual(result, intent)

        # Test actual chaining
        intent.putExtra("a", 1).putExtra("b", 2).putExtra("c", 3)
        self.assertEqual(intent.extras["a"], 1)
        self.assertEqual(intent.extras["b"], 2)
        self.assertEqual(intent.extras["c"], 3)

    def test_put_extra_overwrites(self):
        """Test that putting an extra with the same key overwrites the value."""
        intent = Intent()
        intent.putExtra("key", "original")
        intent.putExtra("key", "updated")
        self.assertEqual(intent.extras["key"], "updated")

    def test_put_extra_various_types(self):
        """Test putting extras of various data types."""
        intent = Intent()
        intent.putExtra("string", "text")
        intent.putExtra("int", 123)
        intent.putExtra("float", 3.14)
        intent.putExtra("bool", True)
        intent.putExtra("list", [1, 2, 3])
        intent.putExtra("dict", {"nested": "value"})
        intent.putExtra("none", None)

        self.assertEqual(intent.extras["string"], "text")
        self.assertEqual(intent.extras["int"], 123)
        self.assertAlmostEqual(intent.extras["float"], 3.14)
        self.assertTrue(intent.extras["bool"])
        self.assertEqual(intent.extras["list"], [1, 2, 3])
        self.assertEqual(intent.extras["dict"]["nested"], "value")
        self.assertIsNone(intent.extras["none"])

    # ============================================================
    # Flag Operations
    # ============================================================

    def test_add_flag_single(self):
        """Test adding a single flag to an intent."""
        intent = Intent()
        intent.addFlag("clear_top")
        self.assertTrue(intent.flags["clear_top"])

    def test_add_flag_with_value(self):
        """Test adding a flag with a specific value."""
        intent = Intent()
        intent.addFlag("no_history", False)
        self.assertFalse(intent.flags["no_history"])

        intent.addFlag("no_animation", True)
        self.assertTrue(intent.flags["no_animation"])

    def test_add_flag_chaining(self):
        """Test that addFlag returns self for method chaining."""
        intent = Intent()
        result = intent.addFlag("clear_top")
        self.assertEqual(result, intent)

        # Test actual chaining
        intent.addFlag("clear_top").addFlag("no_history").addFlag("no_animation")
        self.assertTrue(intent.flags["clear_top"])
        self.assertTrue(intent.flags["no_history"])
        self.assertTrue(intent.flags["no_animation"])

    def test_add_flag_overwrites(self):
        """Test that adding a flag with the same name overwrites the value."""
        intent = Intent()
        intent.addFlag("flag", True)
        intent.addFlag("flag", False)
        self.assertFalse(intent.flags["flag"])

    def test_multiple_flags(self):
        """Test adding multiple different flags."""
        intent = Intent()
        intent.addFlag("clear_top", True)
        intent.addFlag("no_history", False)
        intent.addFlag("custom_flag", True)

        self.assertEqual(len(intent.flags), 3)
        self.assertTrue(intent.flags["clear_top"])
        self.assertFalse(intent.flags["no_history"])
        self.assertTrue(intent.flags["custom_flag"])

    # ============================================================
    # Combined Operations
    # ============================================================

    def test_chaining_extras_and_flags(self):
        """Test chaining both extras and flags together."""
        intent = Intent(action="view")
        intent.putExtra("user_id", 123)\
              .putExtra("username", "alice")\
              .addFlag("clear_top")\
              .addFlag("no_history")

        self.assertEqual(intent.action, "view")
        self.assertEqual(intent.extras["user_id"], 123)
        self.assertEqual(intent.extras["username"], "alice")
        self.assertTrue(intent.flags["clear_top"])
        self.assertTrue(intent.flags["no_history"])

    def test_intent_builder_pattern(self):
        """Test using intent as a builder pattern."""
        class MockActivity:
            pass

        intent = Intent()\
            .putExtra("key1", "value1")\
            .putExtra("key2", 42)\
            .addFlag("clear_top")\
            .addFlag("no_animation", False)

        # Modify after initial creation
        intent.activity_class = MockActivity
        intent.action = "custom_action"
        intent.data = "custom_data"

        self.assertEqual(intent.activity_class, MockActivity)
        self.assertEqual(intent.action, "custom_action")
        self.assertEqual(intent.data, "custom_data")
        self.assertEqual(intent.extras["key1"], "value1")
        self.assertEqual(intent.extras["key2"], 42)
        self.assertTrue(intent.flags["clear_top"])
        self.assertFalse(intent.flags["no_animation"])

    # ============================================================
    # Common Intent Patterns
    # ============================================================

    def test_view_intent_pattern(self):
        """Test creating a typical 'view' intent."""
        intent = Intent(action="view", data="https://micropythonos.com")
        intent.putExtra("fullscreen", True)

        self.assertEqual(intent.action, "view")
        self.assertEqual(intent.data, "https://micropythonos.com")
        self.assertTrue(intent.extras["fullscreen"])

    def test_share_intent_pattern(self):
        """Test creating a typical 'share' intent."""
        intent = Intent(action="share")
        intent.putExtra("text", "Check out MicroPythonOS!")
        intent.putExtra("subject", "Cool OS")

        self.assertEqual(intent.action, "share")
        self.assertEqual(intent.extras["text"], "Check out MicroPythonOS!")
        self.assertEqual(intent.extras["subject"], "Cool OS")

    def test_launcher_intent_pattern(self):
        """Test creating a typical launcher intent."""
        intent = Intent(action="main")
        intent.addFlag("clear_top")

        self.assertEqual(intent.action, "main")
        self.assertTrue(intent.flags["clear_top"])

    def test_scan_qr_intent_pattern(self):
        """Test creating a scan QR code intent (from camera app)."""
        intent = Intent(action="scan_qr_code")
        intent.putExtra("result_key", "qr_data")

        self.assertEqual(intent.action, "scan_qr_code")
        self.assertEqual(intent.extras["result_key"], "qr_data")

    # ============================================================
    # Edge Cases
    # ============================================================

    def test_empty_strings(self):
        """Test intent with empty strings."""
        intent = Intent(action="", data="")
        intent.putExtra("empty", "")

        self.assertEqual(intent.action, "")
        self.assertEqual(intent.data, "")
        self.assertEqual(intent.extras["empty"], "")

    def test_special_characters_in_extras(self):
        """Test extras with special characters in keys."""
        intent = Intent()
        intent.putExtra("key.with.dots", "value1")
        intent.putExtra("key_with_underscores", "value2")
        intent.putExtra("key-with-dashes", "value3")

        self.assertEqual(intent.extras["key.with.dots"], "value1")
        self.assertEqual(intent.extras["key_with_underscores"], "value2")
        self.assertEqual(intent.extras["key-with-dashes"], "value3")

    def test_unicode_in_extras(self):
        """Test extras with Unicode strings."""
        intent = Intent()
        intent.putExtra("greeting", "Hello 世界")
        intent.putExtra("emoji", "🚀")

        self.assertEqual(intent.extras["greeting"], "Hello 世界")
        self.assertEqual(intent.extras["emoji"], "🚀")

    def test_complex_extras_data(self):
        """Test extras with complex nested data structures."""
        intent = Intent()
        complex_data = {
            "users": ["alice", "bob"],
            "config": {
                "timeout": 30,
                "retry": True
            }
        }
        intent.putExtra("data", complex_data)

        self.assertEqual(intent.extras["data"]["users"][0], "alice")
        self.assertEqual(intent.extras["data"]["config"]["timeout"], 30)
        self.assertTrue(intent.extras["data"]["config"]["retry"])


