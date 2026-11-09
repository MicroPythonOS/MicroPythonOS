import ast
import importlib.util
import os
from pathlib import Path
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def test_generic_boot_does_not_force_an_s3_board(self):
        source = (ROOT / "internal_filesystem/lib/mpos/main.py").read_text()
        self.assertNotIn("from mpos.board_config import", source)
        self.assertFalse((ROOT / "internal_filesystem/lib/mpos/board_config.py").exists())

    def manifest_main(self, boot_dir=None):
        frozen = []
        env = {} if boot_dir is None else {"MPOS_BOOT_DIR": boot_dir}
        with patch.dict(os.environ, env, clear=True):
            exec((ROOT / "manifests/manifest.py").read_text(), {
                "freeze": lambda directory, name: frozen.append((directory, name)),
                "package": lambda *args, **kwargs: None,
            })
        return [entry for entry in frozen if entry[1] == "main.py"]

    def test_generic_manifest_uses_standard_boot(self):
        self.assertEqual(self.manifest_main(), [("../internal_filesystem/", "main.py")])

    def test_custom_manifest_is_explicit(self):
        self.assertEqual(self.manifest_main("/project/tmp/board-boot"),
                         [("/project/tmp/board-boot", "main.py")])

    def test_generated_boot_selects_board_before_os_import(self):
        path = ROOT / "scripts/d_shell/prepare_boot.py"
        spec = importlib.util.spec_from_file_location("prepare_boot", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = (ROOT / "internal_filesystem/main.py").read_text()
        generated = module.prepare_boot(original)
        tree = ast.parse(generated)
        startup = next(node for node in tree.body if isinstance(node, ast.Try)
                       and any(isinstance(child, ast.Import) and child.names[0].name == "mpos.main"
                               for child in node.body))
        selected = []
        device = types.SimpleNamespace(hardware_id="missing-hardware-info",
                                       set_hardware_id=lambda name: selected.append(name))
        fake = types.ModuleType("mpos.device_info")
        fake.DeviceInfo = device
        nodes = startup.body[:-1]
        with patch.dict("sys.modules", {"mpos.device_info": fake}):
            exec(compile(ast.Module(body=nodes, type_ignores=[]), "boot", "exec"), {})
        self.assertEqual(selected, ["d_shell"])
        selected.clear()
        device.hardware_id = "another_explicit_board"
        with patch.dict("sys.modules", {"mpos.device_info": fake}):
            exec(compile(ast.Module(body=nodes, type_ignores=[]), "boot", "exec"), {})
        self.assertEqual(selected, [])
        self.assertNotIn("set_hardware_id", original)


if __name__ == "__main__":
    unittest.main()
