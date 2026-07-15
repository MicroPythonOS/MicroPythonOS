"""test_uaiowebsocket_backoff.py - Unit tests for the reconnect backoff helper.

Verifies uaiowebsocket._next_backoff (the pure function driving the relay
reconnect loop) grows geometrically toward the cap while a relay stays
unreachable, and snaps back to the minimum once a live connection closes.

Network-free: only imports the pure helper, no sockets or event loop.

Usage:
"""

import sys
import unittest

sys.path.insert(0, '../internal_filesystem/lib')

from uaiowebsocket import _next_backoff, _RECONNECT_MAX_S

MIN_S = 3


class TestReconnectBackoff(unittest.TestCase):

    def test_first_failure_doubles_min(self):
        """A failure from the seed interval doubles it, staying below the cap."""
        self.assertEqual(_next_backoff(MIN_S, False, MIN_S), 6)

    def test_geometric_growth_to_cap(self):
        """Repeated failures double the delay until clamped at the max."""
        expected = [6, 12, 24, 48, 96, 192, 300, 300, 300]
        delay = MIN_S
        seen = []
        for _ in range(len(expected)):
            delay = _next_backoff(delay, False, MIN_S)
            seen.append(delay)
        self.assertEqual(seen, expected)

    def test_never_exceeds_max(self):
        """A delay already at the cap cannot grow past it."""
        self.assertEqual(_next_backoff(_RECONNECT_MAX_S, False, MIN_S), _RECONNECT_MAX_S)

    def test_reset_on_live_connection(self):
        """A session that actually connected resets the delay to the seed min."""
        self.assertEqual(_next_backoff(_RECONNECT_MAX_S, True, MIN_S), MIN_S)
        self.assertEqual(_next_backoff(192, True, MIN_S), MIN_S)

    def test_seed_min_is_honored(self):
        """A custom (larger) reconnect interval is used as the floor on reset."""
        self.assertEqual(_next_backoff(48, True, 5), 5)
        self.assertEqual(_next_backoff(5, False, 5), 10)


if __name__ == "__main__":
    unittest.main()
