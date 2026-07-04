"""
Regression test for the SpaceInvaders level-skip bug.

After clearing all invaders _check_level_complete() was previously called once
per frame while a delayed timer waited ~500 ms to start the next level. Because
the game state stayed "playing", it incremented self.level on every frame,
jumping from level 1 to around level 16.

This test verifies that clearing a level advances the level by exactly one,
regardless of how many times _check_level_complete() is invoked.
"""

import time
import unittest

from mpos import AppManager, wait_for_render


def _wait(predicate, timeout_ms=3000):
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while not predicate():
        if time.ticks_diff(time.ticks_ms(), deadline) > 0:
            return False
        wait_for_render(1)
    return True


class TestSpaceInvadersLevelComplete(unittest.TestCase):
    """Regression test for level-complete advancement."""

    def setUp(self):
        """Return to launcher before each test."""
        AppManager.restart_launcher()
        wait_for_render(10)

    def tearDown(self):
        """Navigate back to launcher after each test."""
        try:
            from mpos import ui

            ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_level_complete_advances_by_one(self):
        """Clearing a level should advance to the next level exactly once."""
        import mpos.ui.view as view

        result = AppManager.start_app("com.micropythonos.space_invaders")
        self.assertTrue(result, "SpaceInvaders should start")
        wait_for_render(10)

        activity = view.screen_stack[-1][0]

        activity._start_game()
        self.assertTrue(
            _wait(lambda: activity.game_state == "playing" and len(activity.invaders) > 0),
            "Game should be playing with invaders",
        )

        self.assertEqual(activity.level, 1)
        self.assertEqual(activity.game_state, "playing")
        self.assertTrue(len(activity.invaders) > 0)

        # Stop the per-frame update timer so background frames do not race
        # with our direct calls to _check_level_complete().
        if activity.update_timer:
            activity.update_timer.delete()
            activity.update_timer = None

        # Kill all invaders to simulate clearing the level.
        for invader in activity.invaders:
            invader["alive"] = False

        # First check should advance to level 2 and enter level-complete state.
        activity._check_level_complete()
        self.assertEqual(activity.level, 2)
        self.assertEqual(activity.game_state, "level_complete")

        # Simulate many subsequent frames before the delayed level start fires.
        for _ in range(20):
            activity._check_level_complete()

        # The level must not advance more than once.
        self.assertEqual(activity.level, 2)
