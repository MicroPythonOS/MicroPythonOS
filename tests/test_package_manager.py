import unittest

from mpos import App, PackageManager

class TestCompareVersions(unittest.TestCase):

    def test_lower_short(self):
        self.assertFalse(PackageManager.compare_versions("1" , "4"))

    def test_lower(self):
        self.assertFalse(PackageManager.compare_versions("1.2.3" , "4.5.6"))

    def test_equal(self):
        self.assertFalse(PackageManager.compare_versions("1.2.3" , "1.2.3"))

    def test_higher(self):
        self.assertTrue(PackageManager.compare_versions("4.5.6", "1.2.3"))
    
    def test_higher_medium_and_long(self):
        self.assertTrue(PackageManager.compare_versions("4.5", "1.2.3"))
    
    def test_words(self):
        self.assertFalse(PackageManager.compare_versions("weird" , "input"))

    def test_one_empty(self):
        self.assertFalse(PackageManager.compare_versions("1.2.3" , ""))

class TestPackageManager_is_installed_by_name(unittest.TestCase):

    def test_installed_builtin(self):
        self.assertTrue(PackageManager.is_installed_by_name("com.micropythonos.appstore"))

    def test_installed_not_builtin(self):
        self.assertTrue(PackageManager.is_installed_by_name("com.micropythonos.helloworld"))

    def test_not_installed(self):
        self.assertFalse(PackageManager.is_installed_by_name("com.micropythonos.badname"))

class TestPackageManager_get_app_list(unittest.TestCase):

    def test_get_app_list(self):
        app_list = PackageManager.get_app_list()
        self.assertGreaterEqual(len(app_list), 13) # more if the symlinks in internal_filesystem/app aren't dangling

    def test_get_app(self):
        app_list = PackageManager.get_app_list()
	hello_world_app = PackageManager.get("com.micropythonos.helloworld")
        self.assertIsInstance(hello_world_app, App)
	self.assertEqual(hello_world_app.icon_path, "apps/com.micropythonos.helloworld/res/mipmap-mdpi/icon_64x64.png")
	self.assertEqual(len(hello_world_app.icon_data), 5378)
