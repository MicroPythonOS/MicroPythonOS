"""Device-safe unittest helper for graphical on-device tests.

MicroPython's unittest.main harness can hard-fault the device when tests
launch apps that start background services/timers (e.g. Nostr Chat) or run
long app-launch loops. The same test logic succeeds when invoked directly on
a TestCase instance, so the crash is in the harness, not the tests.

This module provides a drop-in replacement for ``unittest.main`` that the
test runner will call (because the runner invokes ``unittest.main(module=...)
``). On desktop (module is ``None`` or ``"__main__"``) it delegates to the
real unittest. On device it executes test methods directly:
``setUp -> test_* -> tearDown``, catching exceptions and reporting results
in the format the runner expects (``TEST WAS A SUCCESS`` / ``TEST WAS A
FAILURE``).

Usage in a test file:

    import unittest
    import _mpos_device_unittest  # noqa: F401

    class MyTests(unittest.TestCase):
        ...

    if __name__ == "__main__":
        unittest.main()
"""

import io
import sys
import unittest

_orig_unittest_main = unittest.main


class _SimpleResult:
    def __init__(self):
        self.testsRun = 0
        self.failuresNum = 0
        self.errorsNum = 0
        self.skippedNum = 0
        self.failures = []
        self.errors = []

    def wasSuccessful(self):
        return self.failuresNum == 0 and self.errorsNum == 0


def _mpos_safe_main(module=None, testRunner=None, **kwargs):
    """Delegate to real unittest.main on desktop; run tests directly on device."""
    if module is None or module == "__main__":
        return _orig_unittest_main(module, testRunner, **kwargs)

    result = _SimpleResult()
    for cls_name in dir(module):
        cls = getattr(module, cls_name)
        if not isinstance(cls, type):
            continue
        if not issubclass(cls, unittest.TestCase):
            continue
        if cls is unittest.TestCase:
            continue

        instance = cls()
        set_up = getattr(instance, "setUp", lambda: None)
        tear_down = getattr(instance, "tearDown", lambda: None)

        for name in dir(instance):
            if not name.startswith("test"):
                continue
            method = getattr(instance, name)
            if not callable(method):
                continue

            print("%s (%s.%s) ..." % (name, module.__name__, cls_name), end="")
            result.testsRun += 1
            try:
                set_up()
                method()
                print(" ok")
            except unittest.SkipTest as e:
                result.skippedNum += 1
                print(" skipped:", e)
            except AssertionError as e:
                result.failuresNum += 1
                result.failures.append((name, str(e)))
                print(" FAIL")
            except Exception as e:  # noqa: BLE001
                result.errorsNum += 1
                buf = io.StringIO()
                sys.print_exception(e, buf)
                result.errors.append((name, buf.getvalue()))
                print(" ERROR")
            finally:
                try:
                    tear_down()
                except Exception:  # noqa: BLE001
                    pass
    return result


def patch_unittest_main():
    """No-op re-export so test files can ``from _mpos_device_unittest import patch_unittest_main``.

    The module already applies the patch on import; calling this function is
    optional and simply returns the replacement.
    """
    return _mpos_safe_main


unittest.main = _mpos_safe_main
