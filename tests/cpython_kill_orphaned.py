#!/usr/bin/env python3
"""
CPython unit tests for ProcessBackend orphan cleanup without /proc (macOS).

The process table is faked, so no MPOS binary is started and nothing real
is signalled.

Usage:
    python3 tests/cpython_kill_orphaned.py
"""

import os
import signal
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts import mpos_controller
from scripts.mpos_controller import ProcessBackend


OWN_PID = os.getpid()
LIVE_PARENTS = {1, 5000, 5001}
DEAD_PARENT = 9999

# (pid, ppid, comm, args) as macOS ps reports them: comm is argv[0], and a
# shebang script shows up as its interpreter.
PROCESSES = [
    (101, 1, "/Users/a/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_macOS",
     "/Users/a/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_macOS -X heapsize=32M"),
    (102, 5000, "/Users/b/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_macOS",
     "/Users/b/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_macOS -X heapsize=32M"),
    (103, DEAD_PARENT, "./lvgl_micropy_macOS", "./lvgl_micropy_macOS"),
    (104, 1, "/bin/bash", "/bin/bash ./scripts/run_desktop.sh"),
    (105, 5001, "/bin/bash", "/bin/bash ./scripts/run_desktop.sh"),
    (106, 1, "/bin/bash", "/bin/bash -c timeout 30 ./scripts/run_desktop.sh"),
    (107, 1, "/usr/bin/vim", "vim run_desktop.sh"),
    (108, 1, "/Applications/Some App.app/Contents/MacOS/Some App",
     "/Applications/Some App.app/Contents/MacOS/Some App"),
    (OWN_PID, 1, "lvgl_micropy_macOS", "lvgl_micropy_macOS"),
]


class FakeSystem:
    def __init__(self):
        self.killed = set()
        self.by_pid = {p[0]: p for p in PROCESSES}

    def _alive(self, pid):
        return pid in LIVE_PARENTS or (pid in self.by_pid and pid not in self.killed)

    def kill(self, pid, sig):
        pid = int(pid)
        if not self._alive(pid):
            raise ProcessLookupError(pid)
        if sig == signal.SIGKILL:
            self.killed.add(pid)

    def run(self, cmd, *args, **kwargs):
        text = kwargs.get("text") or kwargs.get("universal_newlines")
        out = ""
        if cmd[0] in ("killall", "pkill"):
            name = cmd[-1]
            for pid, _ppid, comm, _args in PROCESSES:
                if os.path.basename(comm) == name:
                    self.killed.add(pid)
        elif cmd[0] == "ps" and "-p" in cmd:
            pid = int(cmd[cmd.index("-p") + 1])
            if pid in self.by_pid and pid not in self.killed:
                out = self.by_pid[pid][3] + "\n"
        elif cmd[0] == "ps":
            out = "".join(
                "{:>5} {:>5} {}\n".format(pid, ppid, comm)
                for pid, ppid, comm, _args in PROCESSES
                if pid not in self.killed
            )
        else:
            raise AssertionError("unexpected command: {}".format(cmd))
        return subprocess.CompletedProcess(cmd, 0, out if text else out.encode(), "" if text else b"")


class TestKillOrphanedWithoutProc(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSystem()
        real_isdir = os.path.isdir
        patches = [
            mock.patch.object(mpos_controller.os.path, "isdir",
                              side_effect=lambda p: False if p == "/proc" else real_isdir(p)),
            mock.patch.object(mpos_controller.os, "kill", side_effect=self.fake.kill),
            mock.patch.object(mpos_controller.subprocess, "run", side_effect=self.fake.run),
            mock.patch.object(mpos_controller.time, "sleep"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_binary_with_live_non_init_parent_is_not_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_macOS")
        self.assertNotIn(102, self.fake.killed)

    def test_binary_with_init_parent_is_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_macOS")
        self.assertIn(101, self.fake.killed)

    def test_binary_with_dead_parent_is_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_macOS")
        self.assertIn(103, self.fake.killed)

    def test_own_process_is_never_killed(self):
        ProcessBackend._kill_orphaned("lvgl_micropy_macOS")
        self.assertNotIn(OWN_PID, self.fake.killed)

    def test_orphaned_shebang_script_is_killed(self):
        ProcessBackend._kill_orphaned("run_desktop.sh")
        self.assertIn(104, self.fake.killed)

    def test_script_with_live_parent_is_not_killed(self):
        ProcessBackend._kill_orphaned("run_desktop.sh")
        self.assertNotIn(105, self.fake.killed)

    def test_script_named_only_in_later_arguments_is_not_killed(self):
        ProcessBackend._kill_orphaned("run_desktop.sh")
        self.assertNotIn(106, self.fake.killed)
        self.assertNotIn(107, self.fake.killed)

    def test_stale_cleanup_spares_other_sessions(self):
        ProcessBackend._kill_stale_processes(
            "/Users/a/MicroPythonOS/lvgl_micropython/build/lvgl_micropy_macOS")
        self.assertEqual(self.fake.killed, {101, 103, 104})


if __name__ == "__main__":
    unittest.main()
