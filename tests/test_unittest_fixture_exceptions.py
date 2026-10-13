# Regression test for unittest's handling of exceptions raised in fixtures:
# setUp, tearDown, cleanups, setUpClass and tearDownClass.
#
# A SkipTest (self.skipTest()) or any other exception raised in a fixture
# used to propagate out of TestSuite.run / TextTestRunner.run /
# unittest.main(), aborting the whole file's run so later tests and classes
# never ran. Now it is recorded as a skip or an error and the run carries on,
# with CPython's semantics for what still runs after a fixture fails.
#
# The nested test classes are defined inside the test methods rather than at
# module level so the outer test runner doesn't collect and run them itself.
import unittest


class TestFixtureExceptions(unittest.TestCase):

    def _run_nested(self, *classes):
        suite = unittest.TestSuite()
        for cls in classes:
            suite.addTest(cls)
        print("\n--- nested run: the skips and errors below are expected ---")
        try:
            result = unittest.TextTestRunner().run(suite)
        except Exception as e:
            # Raise AssertionError directly: an escaped SkipTest would
            # otherwise mark this test skipped instead of failed.
            raise AssertionError("fixture exception escaped TextTestRunner.run: %r" % e)
        print("--- end of nested run ---")
        return result

    def _assert_errors_mention(self, result, texts):
        self.assertEqual(len(result.errors), len(texts))
        for (_test, traceback_text), text in zip(result.errors, texts):
            self.assertIn(text, traceback_text)

    def test_setup_exceptions_do_not_abort_run(self):
        events = []

        class SkipInSetUp(unittest.TestCase):
            def setUp(self):
                self.addCleanup(events.append, "skip:cleanup")
                self.skipTest("skipped from setUp (expected)")

            def tearDown(self):
                events.append("skip:tearDown")

            def test_body(self):
                events.append("skip:body")

        class ErrorInSetUp(unittest.TestCase):
            def setUp(self):
                raise RuntimeError("raised from setUp (expected by this test)")

            def tearDown(self):
                events.append("error:tearDown")

            def test_first(self):
                events.append("error:body")

            def test_second(self):
                events.append("error:body")

        class RunsAfter(unittest.TestCase):
            def setUp(self):
                events.append("after:setUp")

            def tearDown(self):
                events.append("after:tearDown")

            def test_body(self):
                events.append("after:body")

        result = self._run_nested(SkipInSetUp, ErrorInSetUp, RunsAfter)

        self.assertEqual(result.testsRun, 4)
        self.assertEqual(result.skippedNum, 1)
        self.assertEqual(result.errorsNum, 2)
        self.assertEqual(result.failuresNum, 0)
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(result.skipped[0][1], "skipped from setUp (expected)")
        self._assert_errors_mention(result, ["raised from setUp", "raised from setUp"])
        self.assertFalse(result.wasSuccessful())

        # The class after the failing setUps still ran, in full.
        self.assertEqual(
            events.count("after:setUp") + events.count("after:body") + events.count("after:tearDown"),
            3,
        )
        # Neither the test body nor tearDown ran when setUp failed, but
        # cleanups added before the failure did.
        self.assertFalse("skip:body" in events)
        self.assertFalse("skip:tearDown" in events)
        self.assertFalse("error:body" in events)
        self.assertFalse("error:tearDown" in events)
        self.assertEqual(events.count("skip:cleanup"), 1)

    def test_teardown_and_cleanup_exceptions_do_not_abort_run(self):
        events = []

        class ErrorInTearDown(unittest.TestCase):
            def tearDown(self):
                events.append("teardown:tearDown")
                raise RuntimeError("raised from tearDown (expected by this test)")

            def test_body(self):
                self.addCleanup(events.append, "teardown:cleanup")
                events.append("teardown:body")

        class ErrorInCleanup(unittest.TestCase):
            def _raise(self):
                raise RuntimeError("raised from a cleanup (expected by this test)")

            def test_body(self):
                # Cleanups run last in, first out: the one added first must
                # still run after the one added second raises.
                self.addCleanup(events.append, "cleanup:added-first")
                self.addCleanup(self._raise)
                self.addCleanup(events.append, "cleanup:added-last")

        class RunsAfter(unittest.TestCase):
            def test_body(self):
                events.append("after:body")

        result = self._run_nested(ErrorInTearDown, ErrorInCleanup, RunsAfter)

        self.assertEqual(result.testsRun, 3)
        self.assertEqual(result.skippedNum, 0)
        self.assertEqual(result.errorsNum, 2)
        self.assertEqual(result.failuresNum, 0)
        self._assert_errors_mention(result, ["raised from tearDown", "raised from a cleanup"])
        self.assertEqual(
            events,
            [
                "teardown:body",
                "teardown:tearDown",
                "teardown:cleanup",
                "cleanup:added-last",
                "cleanup:added-first",
                "after:body",
            ],
        )

    def test_class_fixture_exceptions_do_not_abort_run(self):
        events = []

        class SkipInSetUpClass(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise unittest.SkipTest("skipped from setUpClass (expected)")

            @classmethod
            def tearDownClass(cls):
                events.append("skipclass:tearDownClass")

            def test_body(self):
                events.append("skipclass:body")

        class ErrorInSetUpClass(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise RuntimeError("raised from setUpClass (expected by this test)")

            @classmethod
            def tearDownClass(cls):
                events.append("errorclass:tearDownClass")

            def test_body(self):
                events.append("errorclass:body")

        class ErrorInTearDownClass(unittest.TestCase):
            @classmethod
            def tearDownClass(cls):
                events.append("teardownclass:tearDownClass")
                raise RuntimeError("raised from tearDownClass (expected by this test)")

            def test_body(self):
                events.append("teardownclass:body")

        class RunsAfter(unittest.TestCase):
            def test_body(self):
                events.append("after:body")

        result = self._run_nested(
            SkipInSetUpClass, ErrorInSetUpClass, ErrorInTearDownClass, RunsAfter
        )

        # As in CPython, a class whose setUpClass fails is reported once,
        # and none of its tests (nor its tearDownClass) run.
        self.assertEqual(result.testsRun, 2)
        self.assertEqual(result.skippedNum, 1)
        self.assertEqual(result.errorsNum, 2)
        self.assertEqual(result.failuresNum, 0)
        self.assertEqual(result.skipped[0][1], "skipped from setUpClass (expected)")
        self._assert_errors_mention(result, ["raised from setUpClass", "raised from tearDownClass"])
        self.assertEqual(
            events,
            ["teardownclass:body", "teardownclass:tearDownClass", "after:body"],
        )

    def test_skip_in_setup_via_main_reports_skip(self):
        # unittest.main(module) goes through TestSuite._load_module and
        # TestRunner.run, the path the test runner uses for whole files.
        class FakeModule:
            __name__ = "fake_module_for_setup_skip"

        class SkipsInSetUp(unittest.TestCase):
            def setUp(self):
                self.skipTest("skipped from setUp (expected)")

            def test_body(self):
                pass

        class StillRuns(unittest.TestCase):
            def test_body(self):
                pass

        FakeModule.SkipsInSetUp = SkipsInSetUp
        FakeModule.StillRuns = StillRuns

        print("\n--- nested unittest.main(): 1 skip below is expected ---")
        try:
            result = unittest.main(module=FakeModule)
        except Exception as e:
            raise AssertionError("setUp exception escaped unittest.main: %r" % e)
        print("--- end of nested run ---")

        self.assertEqual(result.testsRun, 2)
        self.assertEqual(result.skippedNum, 1)
        self.assertEqual(result.errorsNum, 0)
        self.assertEqual(result.failuresNum, 0)
        self.assertTrue(result.wasSuccessful())


if __name__ == "__main__":
    unittest.main()
