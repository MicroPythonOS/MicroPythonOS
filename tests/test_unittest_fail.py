# Regression test: unittest's failure helpers must raise AssertionError even
# when unittest was compiled with mpy-cross -O3.
#
# The desktop build freezes internal_filesystem/lib with -O3, which strips
# `assert` statements, and boot imports that frozen unittest. TestCase.fail()
# (`assert False, msg`), assertRaises() as a context manager and
# expectedFailure() were silent no-ops there, so a test that called
# self.fail() passed. A missing AssertionError is reported here with
# RuntimeError, which -O3 can't strip, so this file errors on such a build
# instead of passing vacuously.
import unittest


def _assertion_raised_by(what, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except AssertionError as e:
        return e
    raise RuntimeError("%s did not raise AssertionError" % what)


class TestFail(unittest.TestCase):

    def test_fail_raises_with_message(self):
        e = _assertion_raised_by("self.fail('probe')", self.fail, "probe")
        self.assertEqual(str(e), "probe")

    def test_fail_raises_without_message(self):
        _assertion_raised_by("self.fail()", self.fail)


class TestAssertRaises(unittest.TestCase):

    def test_context_manager_fails_when_nothing_raised(self):
        def no_exception():
            with self.assertRaises(ValueError):
                pass

        _assertion_raised_by("assertRaises() context manager", no_exception)

    def test_context_manager_catches_expected_exception(self):
        with self.assertRaises(ValueError) as cm:
            raise ValueError("expected")
        self.assertEqual(str(cm.exception), "expected")

    def test_callable_fails_when_nothing_raised(self):
        _assertion_raised_by("assertRaises(exc, func)", self.assertRaises, ValueError, lambda: None)


class TestExpectedFailure(unittest.TestCase):

    def test_unexpected_success_fails(self):
        _assertion_raised_by("expectedFailure on a passing function", unittest.expectedFailure(lambda: None))

    def test_expected_failure_passes(self):
        def failing():
            raise AssertionError("expected")

        unittest.expectedFailure(failing)()


class TestAssertMethods(unittest.TestCase):

    def test_each_assert_method_passes_and_fails(self):
        obj = object()
        # (method, args that pass, args that fail)
        cases = (
            ("assertEqual", (1, 1), (1, 2)),
            ("assertNotEqual", (1, 2), (1, 1)),
            ("assertLessEqual", (1, 1), (2, 1)),
            ("assertGreaterEqual", (1, 1), (1, 2)),
            ("assertAlmostEqual", (1.0, 1.00000001), (1.0, 1.1)),
            ("assertNotAlmostEqual", (1.0, 1.1), (1.0, 1.00000001)),
            ("assertIs", (obj, obj), (obj, object())),
            ("assertIsNot", (obj, object()), (obj, obj)),
            ("assertIsNone", (None,), (0,)),
            ("assertIsNotNone", (0,), (None,)),
            ("assertTrue", (1,), (0,)),
            ("assertFalse", (0,), (1,)),
            ("assertIn", (1, (1, 2)), (3, (1, 2))),
            ("assertIsInstance", (1, int), (1, str)),
        )
        for name, passing, failing in cases:
            method = getattr(self, name)
            method(*passing)
            _assertion_raised_by("%s%r" % (name, failing), method, *failing)

    def test_almost_equal_delta(self):
        self.assertAlmostEqual(1.0, 1.5, delta=0.5)
        _assertion_raised_by("assertAlmostEqual delta", self.assertAlmostEqual, 1.0, 2.0, delta=0.5)
        self.assertNotAlmostEqual(1.0, 2.0, delta=0.5)
        _assertion_raised_by("assertNotAlmostEqual delta", self.assertNotAlmostEqual, 1.0, 1.5, delta=0.5)

    def test_custom_message_is_kept(self):
        e = _assertion_raised_by("assertEqual with msg", self.assertEqual, 1, 2, "custom message")
        self.assertEqual(str(e), "custom message")
