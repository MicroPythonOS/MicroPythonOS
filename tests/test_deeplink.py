import unittest

from mpos.content import deeplink
from mpos.content.app_manager import AppManager


class TestParseStoreLink(unittest.TestCase):
    """Parser tests for official app-store deep links."""

    def test_canonical_https_link(self):
        link = deeplink.parse_store_link("https://apps.micropythonos.com/app/com.example.paint")
        self.assertIsNotNone(link)
        self.assertEqual(link["fullname"], "com.example.paint")
        self.assertIsNone(link["min_version"])
        self.assertIsNone(link["source"])

    def test_query_params(self):
        link = deeplink.parse_store_link(
            "https://apps.micropythonos.com/app/com.example.paint?v=1.2.3&s=badge")
        self.assertEqual(link["fullname"], "com.example.paint")
        self.assertEqual(link["min_version"], "1.2.3")
        self.assertEqual(link["source"], "badge")

    def test_unknown_params_ignored(self):
        link = deeplink.parse_store_link(
            "https://apps.micropythonos.com/app/com.example.paint?x=1&v=2")
        self.assertEqual(link["fullname"], "com.example.paint")
        self.assertEqual(link["min_version"], "2")

    def test_invalid_version_param_dropped(self):
        link = deeplink.parse_store_link(
            "https://apps.micropythonos.com/app/com.example.paint?v=1.2evil")
        self.assertIsNotNone(link)
        self.assertIsNone(link["min_version"])

    def test_custom_scheme_alias(self):
        link = deeplink.parse_store_link("micropythonos://app/com.example.paint")
        self.assertIsNotNone(link)
        self.assertEqual(link["fullname"], "com.example.paint")

    def test_uppercase_qr_alphanumeric_mode(self):
        # QR codes in alphanumeric mode encode everything uppercase.
        link = deeplink.parse_store_link("HTTPS://APPS.MICROPYTHONOS.COM/APP/COM.EXAMPLE.PAINT")
        self.assertIsNotNone(link)
        self.assertEqual(link["fullname"], "com.example.paint")

    def test_surrounding_whitespace_stripped(self):
        link = deeplink.parse_store_link("  https://apps.micropythonos.com/app/com.example.paint\n")
        self.assertIsNotNone(link)

    def test_fragment_discarded(self):
        link = deeplink.parse_store_link("https://apps.micropythonos.com/app/com.example.paint#frag")
        self.assertIsNotNone(link)
        self.assertEqual(link["fullname"], "com.example.paint")

    def test_rejects_http(self):
        self.assertIsNone(deeplink.parse_store_link("http://apps.micropythonos.com/app/com.example.paint"))

    def test_rejects_lookalike_host_suffix(self):
        self.assertIsNone(deeplink.parse_store_link(
            "https://apps.micropythonos.com.evil.example/app/com.example.paint"))

    def test_rejects_lookalike_host_prefix(self):
        self.assertIsNone(deeplink.parse_store_link(
            "https://evilapps.micropythonos.com.example/app/com.example.paint"))

    def test_rejects_userinfo_trick(self):
        self.assertIsNone(deeplink.parse_store_link(
            "https://apps.micropythonos.com@evil.example/app/com.example.paint"))

    def test_rejects_port(self):
        self.assertIsNone(deeplink.parse_store_link(
            "https://apps.micropythonos.com:8443/app/com.example.paint"))

    def test_rejects_wrong_path_prefix(self):
        self.assertIsNone(deeplink.parse_store_link("https://apps.micropythonos.com/repo/x"))
        self.assertIsNone(deeplink.parse_store_link("https://apps.micropythonos.com/"))

    def test_rejects_subpath_and_traversal(self):
        self.assertIsNone(deeplink.parse_store_link(
            "https://apps.micropythonos.com/app/com.example.paint/extra"))
        self.assertIsNone(deeplink.parse_store_link(
            "https://apps.micropythonos.com/app/../etc"))

    def test_rejects_empty_or_bad_charset_id(self):
        self.assertIsNone(deeplink.parse_store_link("https://apps.micropythonos.com/app/"))
        self.assertIsNone(deeplink.parse_store_link("https://apps.micropythonos.com/app/bad%20id"))
        self.assertIsNone(deeplink.parse_store_link("https://apps.micropythonos.com/app/spa ce"))

    def test_rejects_overlong_input(self):
        self.assertIsNone(deeplink.parse_store_link(
            "https://apps.micropythonos.com/app/" + "a" * 600))
        self.assertIsNone(deeplink.parse_store_link(
            "https://apps.micropythonos.com/app/" + "a" * 65))

    def test_rejects_garbage(self):
        for garbage in (None, 42, "", "hello", "WIFI:T:WPA;S:x;P:y;;",
                        "https://", "://x", "javascript://app/x"):
            self.assertIsNone(deeplink.parse_store_link(garbage))

    def test_rejects_custom_scheme_wrong_form(self):
        self.assertIsNone(deeplink.parse_store_link("micropythonos://repo/xyz"))
        self.assertIsNone(deeplink.parse_store_link("micropythonos://app/"))


class TestHandlerPatternValidation(unittest.TestCase):
    """Reserved-pattern and wildcard rules for manifest urlPattern entries."""

    def test_valid_third_party_patterns(self):
        self.assertIsNone(deeplink.validate_handler_pattern("https://store.acme.example/app/*"))
        self.assertIsNone(deeplink.validate_handler_pattern("acmestore://open/thing"))

    def test_reserved_store_host_rejected(self):
        self.assertIsNotNone(deeplink.validate_handler_pattern(
            "https://apps.micropythonos.com/app/*"))

    def test_reserved_scheme_rejected(self):
        self.assertIsNotNone(deeplink.validate_handler_pattern("micropythonos://app/*"))

    def test_wildcard_only_at_end(self):
        self.assertIsNotNone(deeplink.validate_handler_pattern("https://*.example/app/x"))
        self.assertIsNotNone(deeplink.validate_handler_pattern("https://a.example/*/x"))

    def test_wildcard_requires_host_and_slash(self):
        self.assertIsNotNone(deeplink.validate_handler_pattern("https://a.example*"))
        self.assertIsNotNone(deeplink.validate_handler_pattern("*"))
        self.assertIsNotNone(deeplink.validate_handler_pattern("https://*"))

    def test_matching(self):
        pat = "https://store.acme.example/app/*"
        self.assertTrue(deeplink.url_matches_pattern(pat, "https://store.acme.example/app/foo"))
        self.assertTrue(deeplink.url_matches_pattern(pat, "HTTPS://STORE.ACME.EXAMPLE/app/foo"))
        self.assertFalse(deeplink.url_matches_pattern(pat, "https://store.acme.example/other"))
        self.assertFalse(deeplink.url_matches_pattern(pat, "https://evil.example/app/foo"))
        exact = "acmestore://open/thing"
        self.assertTrue(deeplink.url_matches_pattern(exact, "acmestore://open/thing"))
        self.assertFalse(deeplink.url_matches_pattern(exact, "acmestore://open/thing2"))


class _FakeHandlerA:
    pass


class _FakeHandlerB:
    pass


class TestUrlHandlerRegistry(unittest.TestCase):
    """AppManager registration and resolution of manifest URL handlers."""

    def setUp(self):
        self._saved_specs = AppManager._url_handler_specs
        self._saved_cache = AppManager._handler_class_cache
        AppManager._url_handler_specs = []
        AppManager._handler_class_cache = {}

    def tearDown(self):
        AppManager._url_handler_specs = self._saved_specs
        AppManager._handler_class_cache = self._saved_cache

    def _register(self, fullname, pattern, handler_cls):
        ok = AppManager._register_url_handler_spec(fullname, "main.py", handler_cls.__name__, pattern)
        if ok:
            # Pre-populate the lazy import cache so resolution needs no real app.
            AppManager._handler_class_cache[(fullname, "main.py", handler_cls.__name__)] = handler_cls
        return ok

    def test_register_and_resolve(self):
        self.assertTrue(self._register("com.acme.store", "https://store.acme.example/app/*", _FakeHandlerA))
        handlers = AppManager.resolve_url_handlers("https://store.acme.example/app/foo")
        self.assertEqual(len(handlers), 1)
        self.assertEqual(handlers[0].activity_class, _FakeHandlerA)
        self.assertEqual(handlers[0].app_fullname, "com.acme.store")

    def test_reserved_pattern_rejected_at_registration(self):
        self.assertFalse(self._register("com.evil.app", "https://apps.micropythonos.com/app/*", _FakeHandlerA))
        self.assertFalse(self._register("com.evil.app", "micropythonos://app/*", _FakeHandlerA))
        self.assertEqual(AppManager._url_handler_specs, [])

    def test_multiple_matches_resolved(self):
        self.assertTrue(self._register("com.acme.store", "https://shared.example/x/*", _FakeHandlerA))
        self.assertTrue(self._register("com.other.store", "https://shared.example/x/*", _FakeHandlerB))
        handlers = AppManager.resolve_url_handlers("https://shared.example/x/y")
        self.assertEqual(len(handlers), 2)

    def test_no_match(self):
        self.assertTrue(self._register("com.acme.store", "https://store.acme.example/app/*", _FakeHandlerA))
        self.assertEqual(AppManager.resolve_url_handlers("https://unrelated.example/app/foo"), [])
        self.assertEqual(AppManager.resolve_url_handlers("not a url"), [])


class TestOpenActionLabel(unittest.TestCase):
    """Chip label decision used by QR scanners (Camera app)."""

    def setUp(self):
        self._saved_specs = AppManager._url_handler_specs
        self._saved_cache = AppManager._handler_class_cache
        AppManager._url_handler_specs = []
        AppManager._handler_class_cache = {}

    def tearDown(self):
        AppManager._url_handler_specs = self._saved_specs
        AppManager._handler_class_cache = self._saved_cache

    def test_store_link(self):
        self.assertEqual(
            deeplink.open_action_label("https://apps.micropythonos.com/app/com.example.paint"),
            "Open in App Store")

    def test_registered_handler(self):
        AppManager._register_url_handler_spec(
            "com.acme.store", "main.py", "_FakeHandlerA", "https://store.acme.example/app/*")
        AppManager._handler_class_cache[("com.acme.store", "main.py", "_FakeHandlerA")] = _FakeHandlerA
        self.assertEqual(
            deeplink.open_action_label("https://store.acme.example/app/foo"), "Open link")

    def test_unhandled(self):
        self.assertIsNone(deeplink.open_action_label("https://unrelated.example/x"))
        self.assertIsNone(deeplink.open_action_label("WIFI:T:WPA;S:x;P:y;;"))
        self.assertIsNone(deeplink.open_action_label(None))


class TestOpenUrl(unittest.TestCase):
    """open_url dispatch: store links go to the AppStore, others to handlers."""

    def setUp(self):
        self._saved_start_app = AppManager.start_app
        self._saved_specs = AppManager._url_handler_specs
        AppManager._url_handler_specs = []
        self.started = []

        def fake_start_app(fullname, intent=None, result_callback=None):
            self.started.append((fullname, intent))
            return True
        AppManager.start_app = fake_start_app

    def tearDown(self):
        AppManager.start_app = self._saved_start_app
        AppManager._url_handler_specs = self._saved_specs

    def test_store_link_starts_appstore_with_extras(self):
        handled = deeplink.open_url("https://apps.micropythonos.com/app/com.example.paint?v=2.0")
        self.assertTrue(handled)
        self.assertEqual(len(self.started), 1)
        fullname, intent = self.started[0]
        self.assertEqual(fullname, deeplink.APPSTORE_FULLNAME)
        self.assertEqual(intent.extras.get("deeplink_fullname"), "com.example.paint")
        self.assertEqual(intent.extras.get("deeplink_min_version"), "2.0")

    def test_unhandled_url_returns_false(self):
        self.assertFalse(deeplink.open_url("https://unknown.example/whatever"))
        self.assertFalse(deeplink.open_url("plain text from a random qr"))
        self.assertEqual(self.started, [])


if __name__ == "__main__":
    unittest.main()
