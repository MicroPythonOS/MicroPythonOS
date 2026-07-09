"""Test REPL Shell output capture. Reproduces sys.stdout assignment bug
on MicroPython and verifies the namespace-based print-capture fix."""

import io
import sys
import unittest


class TestReplOutputCapture(unittest.TestCase):

    def test_sys_stdout_is_readonly(self):
        """Reproduce: sys.stdout assignment raises AttributeError."""
        buf = io.StringIO()
        with self.assertRaises(AttributeError):
            sys.stdout = buf

    def test_namespace_print_capture(self):
        """Fix: capture output by overriding print in exec namespace."""
        ns = {}
        captured = []

        def _print(*args, sep=" ", end="\n"):
            captured.append(sep.join(str(a) for a in args) + end)

        ns["print"] = _print

        exec("print('hello')", ns)
        self.assertEqual("".join(captured), "hello\n")

        exec("x = 42", ns)
        self.assertEqual(ns["x"], 42)

        exec("print(x)", ns)
        self.assertIn("42\n", "".join(captured))

    def test_namespace_persists_variables(self):
        """Variables persist between exec calls using the same namespace."""
        ns = {}
        captured = []

        def _print(*args, sep=" ", end="\n"):
            captured.append(sep.join(str(a) for a in args) + end)

        ns["print"] = _print

        exec("x = 42\ny = x * 2", ns)
        self.assertEqual(ns["x"], 42)
        self.assertEqual(ns["y"], 84)

        exec("print(x, y)", ns)
        self.assertIn("42 84\n", "".join(captured))

    def test_exception_captured(self):
        """Exceptions during exec are caught and reported."""
        ns = {}
        captured = []

        def _print(*args, sep=" ", end="\n"):
            captured.append(sep.join(str(a) for a in args) + end)

        ns["print"] = _print

        try:
            exec("1/0", ns)
        except Exception as e:
            error = "%s: %s" % (type(e).__name__, e)

        self.assertIn("ZeroDivisionError", error)

    def test_partial_output_before_exception(self):
        """Output before an exception is still captured, then the error."""
        ns = {}
        captured = []

        def _print(*args, sep=" ", end="\n"):
            captured.append(sep.join(str(a) for a in args) + end)

        ns["print"] = _print

        code = "print('before')\n1/0\nprint('after')"
        error = None
        try:
            exec(code, ns)
        except Exception as e:
            error = "%s: %s" % (type(e).__name__, e)

        combined = "".join(captured)
        self.assertIn("before", combined)
        self.assertTrue("after" not in combined)
        self.assertIsNotNone(error)

    def test_empty_code_no_capture(self):
        """Empty code produces no captured output."""
        ns = {}
        captured = []

        def _print(*args, sep=" ", end="\n"):
            captured.append(sep.join(str(a) for a in args) + end)

        ns["print"] = _print

        exec("", ns)
        self.assertEqual(captured, [])


if __name__ == "__main__":
    unittest.main()
