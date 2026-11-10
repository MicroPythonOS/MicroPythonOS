from pathlib import Path
import os
import sys
import time

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from scripts.mpos_controller import MPOSController

outdir = root / "tmp/dshell"
outdir.mkdir(parents=True, exist_ok=True)
port = os.environ.get("MPOS_TEST_PORT", str(outdir / "device-tty"))
with MPOSController(backend="serial", port=port, reset=False) as controller:
    time.sleep(8)
    print("Starting D-Shell hardware regression tests", flush=True)
    content = (root / "tests/test_graphical_d_shell_hardware.py").read_bytes()
    controller.exec("import ubinascii; dshell_test_file = open('/_runner_test.py', 'wb')")
    for index in range(0, len(content), 512):
        chunk = content[index:index + 512].hex()
        controller.exec("dshell_test_file.write(ubinascii.unhexlify('%s'))" % chunk)
    controller.exec("dshell_test_file.close()")
    controller.exec("import sys; sys.modules.pop('_runner_test', None); import _runner_test; dshell_case = _runner_test.DShellHardwareTests(); dshell_results = {}; dshell_case.setUp()")
    names = ["test_board_and_display", "test_gt911_identity", "test_buttons_idle", "test_qmi8658",
             "test_aht20", "test_veml7700", "test_ds1307", "test_registered_outputs"]
    output = bytearray()
    for name in names:
        code = "try:\n dshell_case.%s()\n dshell_results['%s'] = 'passed'\nexcept Exception as error:\n dshell_results['%s'] = repr(error)\nprint('%s', dshell_results['%s'])" % (name, name, name, name, name)
        captured = controller.exec_multiline(code, timeout=15)
        output.extend(captured + b"\n")
        print(captured.decode(errors="replace"), flush=True)
    results = controller.eval("dshell_results")
    passed = all(results.get(name) == "passed" for name in names)
    (outdir / "hardware-tests.log").write_bytes(output)
    print(output.decode(errors="replace"), flush=True)
    print("HARDWARE_TESTS_PASSED", passed, flush=True)
    if not passed:
        raise SystemExit(1)
