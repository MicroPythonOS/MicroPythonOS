#!/usr/bin/env python3
"""
CPython unit tests for ProcessBackend orphan cleanup through /proc (Linux).

/proc is faked, so no MPOS binary is started and nothing real is signalled.

Usage:
    python3 tests/cpython_kill_orphaned_linux.py
"""

import io
import os
import signal
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts import mpos_controller
from scripts.mpos_controller import ProcessBackend


OWN_PID = os.getpid()
LIVE_PARENTS = {1, 5000, 5001}
DEAD_PARENT = 9999

# (pid, ppid, comm, argv) as Linux /proc reports them: comm is the basename of
# the executed file cut to 15 characters, so lvgl_micropy_unix shows up as
# lvgl_micropy_un and a shebang script keeps its own name.
PROCESSES = [
    (201, 1, "lvgl_micropy_un",
     ["/home/a/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_unix",
      "-X", "heapsize=32M", "-v", "-i", "-m", "main"]),
    (202, 5000, "lvgl_micropy_un",
     ["/home/b/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_unix",
      "-X", "heapsize=32M", "-v", "-i", "-m", "main"]),
    (203, DEAD_PARENT, "lvgl_micropy_un", ["./lvgl_micropy_unix"]),
    (204, 1, "lvgl_micropy_un", ["/opt/tools/lvgl_micropy_unittest"]),
    (205, 1, "run_desktop.sh", ["/bin/bash", "./scripts/run_desktop.sh"]),
    (206, 5001, "run_desktop.sh", ["/bin/bash", "./scripts/run_desktop.sh"]),
    (207, 1, "bash", ["/bin/bash", "-c", "timeout 30 ./scripts/run_desktop.sh"]),
    (208, 1, "vim", ["vim", "run_desktop.sh"]),
    (209, 1, "lvgl_micropy_un", None),
    (OWN_PID, 1, "lvgl_micropy_un", ["lvgl_micropy_unix"]),
]


class FakeProc:
    def __init__(self):
        self.killed = set()
        self.by_pid = {p[0]: p for p in PROCESSES}

    def _running(self, pid):
        return pid in self.by_pid and pid not in self.killed

    def _alive(self, pid):
        return pid in LIVE_PARENTS or self._running(pid)

    def kill(self, pid, sig):
        pid = int(pid)
        if not self._alive(pid):
            raise ProcessLookupError(pid)
        if sig == signal.SIGKILL:
            self.killed.add(pid)

    def listdir(self, path):
        assert path == "/proc", path
        return ["self", "meminfo"] + [str(pid) for pid in self.by_pid if self._running(pid)]

    def open(self, path, mode="r", *args, **kwargs):
        parts = path.split("/")
        if len(parts) != 4 or parts[1] != "proc" or not parts[2].isdigit():
            raise AssertionError("unexpected open: {}".format(path))
        pid, field = int(parts[2]), parts[3]
        if not self._running(pid):
            raise FileNotFoundError(path)
        _pid, ppid, comm, argv = self.by_pid[pid]
        if field == "comm":
            data = comm + "\n"
        elif field == "status":
            data = "Name:\t{}\nState:\tS (sleeping)\nTgid:\t{}\nPid:\t{}\nPPid:\t{}\n".format(
                comm, pid, pid, ppid)
        elif field == "cmdline":
            if argv is None:
                raise PermissionError(path)
            data = "".join(arg + "\0" for arg in argv)
        else:
            raise AssertionError("unexpected open: {}".format(path))
        if "b" in mode:
            return io.BytesIO(data.encode())
        return io.StringIO(data)


class TestKillOrphanedWithProc(unittest.TestCase):
    def setUp(self):
        self.fake = FakeProc()
        real_isdir = os.path.isdir
        real_listdir = os.listdir
        patches = [
            mock.patch.object(mpos_controller.os.path, "isdir",
                              side_effect=lambda p: True if p == "/proc" else real_isdir(p)),
            mock.patch.object(mpos_controller.os, "listdir",
                              side_effect=lambda p: self.fake.listdir(p) if p == "/proc" else real_listdir(p)),
            mock.patch.object(mpos_controller, "open", side_effect=self.fake.open, create=True),
            mock.patch.object(mpos_controller.os, "kill", side_effect=self.fake.kill),
            mock.patch.object(mpos_controller.subprocess, "run",
                              side_effect=AssertionError("subprocess.run called")),
            mock.patch.object(mpos_controller.time, "sleep"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_binary_with_truncated_comm_and_init_parent_is_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_unix")
        self.assertIn(201, self.fake.killed)

    def test_binary_with_truncated_comm_and_dead_parent_is_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_unix")
        self.assertIn(203, self.fake.killed)

    def test_binary_with_live_non_init_parent_is_not_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_unix")
        self.assertNotIn(202, self.fake.killed)

    def test_other_program_with_same_truncated_comm_is_not_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_unix")
        self.assertNotIn(204, self.fake.killed)

    def test_truncated_comm_with_unreadable_cmdline_is_not_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_unix")
        self.assertNotIn(209, self.fake.killed)

    def test_own_process_is_never_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_unix")
        self.assertNotIn(OWN_PID, self.fake.killed)

    def test_orphaned_shebang_script_is_killed(self):
        ProcessBackend._kill_orphaned("run_desktop.sh")
        self.assertIn(205, self.fake.killed)

    def test_script_with_live_parent_is_not_killed(self):
        ProcessBackend._kill_orphaned("run_desktop.sh")
        self.assertNotIn(206, self.fake.killed)

    def test_script_named_only_in_arguments_is_not_killed(self):
        ProcessBackend._kill_orphaned("run_desktop.sh")
        self.assertNotIn(207, self.fake.killed)
        self.assertNotIn(208, self.fake.killed)

    def test_stale_cleanup_spares_other_sessions(self):
        ProcessBackend._kill_stale_processes(
            "/home/a/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_unix")
        self.assertEqual(self.fake.killed, {201, 203, 205})


if __name__ == "__main__":
    unittest.main()
