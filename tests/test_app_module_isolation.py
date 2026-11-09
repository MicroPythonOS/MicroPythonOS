"""
test_app_module_isolation.py - Verify apps do not share same-named modules.

Issue #262: flat (non-package) apps import their helpers by bare module name.
MicroPython checks sys.modules before sys.path, so the first app to import e.g.
``lora.py`` used to serve that module to every later app with its own
``lora.py``, and an updated app kept running the old helper code.

Usage:
    python3 scripts/test_runner.py tests/test_app_module_isolation.py
"""

import os
import shutil
import sys
import unittest

from mpos import AppManager

APP_A = "com.test.moduleisolation.a"
APP_B = "com.test.moduleisolation.b"
ZIPTEST = "com.micropythonos.ziptest"


class TestAppModuleIsolation(unittest.TestCase):
    def setUp(self):
        self._remove_app(APP_A)
        self._remove_app(APP_B)
        self._remove_app(ZIPTEST)
        try:
            os.stat("data")
        except OSError:
            os.mkdir("data")
        self._remove_module("helper")
        self._remove_module("isolated_main")

    def tearDown(self):
        self._remove_app(APP_A)
        self._remove_app(APP_B)
        self._remove_app(ZIPTEST)
        try:
            os.remove("data/tmp_moduleisolation.mpk")
        except OSError:
            pass
        self._remove_module("helper")
        self._remove_module("isolated_main")
        AppManager.refresh_apps()

    def _remove_module(self, name):
        sys.modules.pop(name, None)

    def _remove_app(self, fullname):
        path = "apps/" + fullname
        try:
            shutil.rmtree(path)
        except OSError:
            pass

    def _make_app(self, fullname, helper_value):
        root = "apps/" + fullname
        try:
            os.mkdir(root)
        except OSError:
            pass
        with open(root + "/MANIFEST.JSON", "w") as f:
            f.write(
                '{"name":"Iso","publisher":"t","short_description":"x",'
                '"long_description":"x","fullname":"' + fullname +
                '","version":"1.0.0","category":"utilities",'
                '"activities":[{"entrypoint":"isolated_main.py",'
                '"classname":"Main","intent_filters":[{"action":"main",'
                '"category":"launcher"}]}]}'
            )
        self._write_helper(fullname, helper_value)
        # The classname is deliberately missing, so execute_script imports the
        # module (which imports helper) but does not launch an activity.
        with open(root + "/isolated_main.py", "w") as f:
            f.write("import helper\n")

    def _write_helper(self, fullname, value):
        with open("apps/" + fullname + "/helper.py", "w") as f:
            f.write("VALUE = %r\n" % value)

    def _run_app(self, fullname):
        AppManager.refresh_apps()
        return AppManager.execute_script(
            "apps/" + fullname + "/isolated_main.py",
            "__no_such_class__",
            "apps/" + fullname,
            app_fullname=fullname,
        )

    def test_two_apps_can_each_have_their_own_helper(self):
        self._make_app(APP_A, "A")
        self._make_app(APP_B, "B")

        self._run_app(APP_A)
        self.assertEqual(sys.modules["helper"].VALUE, "A")

        self._run_app(APP_B)
        self.assertEqual(
            sys.modules["helper"].VALUE, "B",
            "the second app must import its own same-named helper",
        )

    def test_second_app_helper_not_shared_back_to_first(self):
        self._make_app(APP_A, "A")
        self._make_app(APP_B, "B")

        self._run_app(APP_A)
        self._run_app(APP_B)
        self._run_app(APP_A)
        self.assertEqual(
            sys.modules["helper"].VALUE, "A",
            "going back to the first app must use its own helper",
        )

    def test_uninstall_drops_cached_modules_so_reinstall_runs_new_code(self):
        self._make_app(APP_A, "old")
        self._run_app(APP_A)
        self.assertEqual(sys.modules["helper"].VALUE, "old")

        AppManager.uninstall_app(APP_A)
        self.assertFalse(
            "helper" in sys.modules,
            "uninstall must drop the app's cached modules",
        )

        self._make_app(APP_A, "new")
        self._run_app(APP_A)
        self.assertEqual(
            sys.modules["helper"].VALUE, "new",
            "after an update the relaunch must import the new helper source",
        )

    def test_install_mpk_drops_cached_modules(self):
        class _CachedModule:
            pass

        module = _CachedModule()
        module.__file__ = "apps/%s/helper.py" % ZIPTEST
        sys.modules["helper"] = module

        shutil.copyfile(
            "../tests/%s_flat_new.mpk" % ZIPTEST,
            "data/tmp_moduleisolation.mpk",
        )
        AppManager.install_mpk(
            "data/tmp_moduleisolation.mpk",
            "apps/" + ZIPTEST,
        )

        self.assertFalse(
            "helper" in sys.modules,
            "installing a package must drop the app's cached modules",
        )


if __name__ == "__main__":
    unittest.main()
