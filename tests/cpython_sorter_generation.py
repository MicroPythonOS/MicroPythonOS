#!/usr/bin/env python3
"""CPython tests for the pure Sorter level-generation logic.

The Sorter app is MicroPython/LVGL code, but its solver is pure Python. These
tests extract the solver functions from the app source so they can run without
booting MicroPythonOS. They pin the cooperative-yield behavior that keeps the
USB-CDC console responsive while a level is generated (#347).

Usage:
    python3 tests/cpython_sorter_generation.py
"""

import ast
import os
import random
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SORTER_PATH = os.path.join(
    REPO_ROOT, "internal_filesystem", "apps", "com.micropythonos.sorter", "sorter.py"
)

KEEP_FUNCTIONS = {
    "_is_solved",
    "_can_move",
    "_apply_move",
    "_top_run",
    "_make_lcg",
    "_shuffle_seeded",
    "_solve_path",
    "_solve_path_iter",
    "_generate_level",
    "_generate_level_iter",
    "_level_params",
}


def load_solver():
    with open(SORTER_PATH) as handle:
        tree = ast.parse(handle.read())
    body = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in KEEP_FUNCTIONS)
        or isinstance(node, ast.Assign)
    ]

    class FakeOS:
        @staticmethod
        def listdir(_path):
            return []

    namespace = {"random": random, "os": FakeOS}
    exec(compile(ast.Module(body=body, type_ignores=[]), SORTER_PATH, "exec"), namespace)
    return namespace


class TestSorterGeneration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.solver = load_solver()

    def _rand_for_level(self, level=1):
        seed = 0
        for value in range(20):
            seed = (seed * 31 + value) & 0x7FFFFFFF
        return self.solver["_make_lcg"](seed + level * 10007)

    def test_generate_level_returns_a_solution(self):
        generate = self.solver["_generate_level"]
        params = self.solver["_level_params"]
        for level in (1, 3, 5):
            filled, capacity, extra = params(level)
            tubes, moves = generate(filled, capacity, extra, self._rand_for_level(level))
            self.assertEqual(len(tubes), filled + extra)
            self.assertTrue(moves, "level %s should have a solution" % level)

    def test_solve_path_iter_yields_while_searching(self):
        solve_iter = self.solver["_solve_path_iter"]
        found = []
        ticks = 0
        generator = solve_iter([[0, 1, 0], [1, 0, 1], [], []], 3, 1000,
                               out=found, yield_every=1)
        while True:
            try:
                next(generator)
            except StopIteration:
                break
            ticks += 1
        self.assertTrue(ticks > 0, "solver never yielded to the event loop")
        self.assertTrue(found and found[0], "solver did not record a path")

    def test_generate_level_iter_reports_progress_and_result(self):
        generate_iter = self.solver["_generate_level_iter"]
        params = self.solver["_level_params"]
        filled, capacity, extra = params(1)
        out = []
        attempts = []
        generator = generate_iter(filled, capacity, extra, self._rand_for_level(1), out=out)
        while True:
            try:
                tick = next(generator)
            except StopIteration:
                break
            if tick is not None:
                attempts.append(tick)
        self.assertEqual(attempts, [1])
        self.assertTrue(out and out[0][1], "generator did not record a solution")

    def test_sync_wrapper_still_matches_generator(self):
        generate = self.solver["_generate_level"]
        generate_iter = self.solver["_generate_level_iter"]
        params = self.solver["_level_params"]
        filled, capacity, extra = params(1)
        rand = self._rand_for_level(1)
        tubes, moves = generate(filled, capacity, extra, rand)
        out = []
        generator = generate_iter(filled, capacity, extra, self._rand_for_level(1), out=out)
        for _ in generator:
            pass
        self.assertEqual((tubes, moves), out[0])


if __name__ == "__main__":
    unittest.main()
