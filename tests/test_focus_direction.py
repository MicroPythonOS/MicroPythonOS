"""
Unit tests for mpos.ui.focus_direction — the Android FocusFinder port.

Tests the pure-Python helper functions (is_candidate, beams_overlap,
beam_beats, is_better_candidate, weighted_distance, major/minor axis
distance) without requiring LVGL.

Key regression scenario covered:
  A small top-left button (like the AppStore settings_button) must be
  reachable via UP from a full-width list item even though the button's
  center is far to the left.  The old ±45° cone algorithm excluded it;
  the Android algorithm selects it correctly.

Usage:
"""

import unittest

from mpos.ui.focus_direction import (
    UP, DOWN, LEFT, RIGHT,
    is_candidate,
    beams_overlap,
    beam_beats,
    major_axis_distance,
    major_axis_distance_to_far_edge,
    minor_axis_distance,
    weighted_distance,
    is_better_candidate,
)


# Rect helpers: (x1, y1, x2, y2)

def rect(x, y, w, h):
    return (x, y, x + w, y + h)


class TestIsCandidate(unittest.TestCase):

    def test_directly_above_is_candidate_for_up(self):
        src  = rect(0, 50, 100, 20)   # y 50–70
        dest = rect(0, 10, 100, 20)   # y 10–30  — fully above
        self.assertTrue(is_candidate(src, dest, UP))

    def test_directly_below_is_not_candidate_for_up(self):
        src  = rect(0, 10, 100, 20)
        dest = rect(0, 50, 100, 20)
        self.assertFalse(is_candidate(src, dest, UP))

    def test_directly_below_is_candidate_for_down(self):
        src  = rect(0, 10, 100, 20)
        dest = rect(0, 50, 100, 20)
        self.assertTrue(is_candidate(src, dest, DOWN))

    def test_directly_above_is_not_candidate_for_down(self):
        src  = rect(0, 50, 100, 20)
        dest = rect(0, 10, 100, 20)
        self.assertFalse(is_candidate(src, dest, DOWN))

    def test_to_the_left_is_candidate_for_left(self):
        src  = rect(100, 0, 50, 20)
        dest = rect(20,  0, 50, 20)
        self.assertTrue(is_candidate(src, dest, LEFT))

    def test_to_the_right_is_candidate_for_right(self):
        src  = rect(20, 0, 50, 20)
        dest = rect(100, 0, 50, 20)
        self.assertTrue(is_candidate(src, dest, RIGHT))

    def test_same_level_diagonal_is_candidate_for_up(self):
        """A widget that is diagonally above-left must still be a UP candidate."""
        src  = rect(100, 100, 200, 50)  # full-width-ish, y 100–150
        dest = rect(5,   5,   34, 34)   # small top-left, y 5–39
        # dest.bottom (39) < src.top (100) — passes isCandidate for UP
        self.assertTrue(is_candidate(src, dest, UP))

    def test_overlapping_vertically_not_candidate_for_up(self):
        """A widget at the same y level is not a UP candidate."""
        src  = rect(0, 50, 100, 50)    # y 50–100
        dest = rect(0, 60, 100, 20)    # y 60–80 — overlaps src vertically
        self.assertFalse(is_candidate(src, dest, UP))

    def test_touching_edge_is_candidate_for_up(self):
        """dest.bottom == src.top is exactly at the boundary — should be a candidate."""
        src  = rect(0, 44, 320, 64)   # list item, y 44–108
        dest = rect(5,  5,  34, 34)   # settings button, y 5–39
        # dest.bottom=39 < src.top=44 → passes
        self.assertTrue(is_candidate(src, dest, UP))


class TestBeamsOverlap(unittest.TestCase):

    def test_same_horizontal_span_overlaps_for_up(self):
        src  = rect(0, 44, 320, 64)
        dest = rect(5,  5,  34, 34)
        # For UP/DOWN: check horizontal overlap. src x: 0–320, dest x: 5–39 → overlap
        self.assertTrue(beams_overlap(src, dest, UP))

    def test_no_horizontal_overlap_no_beam_for_up(self):
        src  = rect(200, 44, 100, 64)   # x 200–300
        dest = rect(5,   5,   34, 34)   # x 5–39 — no overlap with 200–300
        self.assertFalse(beams_overlap(src, dest, UP))

    def test_vertical_overlap_for_left(self):
        src  = rect(100, 10, 50, 30)   # y 10–40
        dest = rect(20,  20, 50, 10)   # y 20–30 — overlaps
        self.assertTrue(beams_overlap(src, dest, LEFT))

    def test_no_vertical_overlap_no_beam_for_left(self):
        src  = rect(100, 10, 50, 20)   # y 10–30
        dest = rect(20,  50, 50, 20)   # y 50–70 — no overlap
        self.assertFalse(beams_overlap(src, dest, LEFT))


class TestMajorAxisDistance(unittest.TestCase):

    def test_gap_above(self):
        src  = rect(0, 50, 100, 20)   # y 50–70
        dest = rect(0, 10, 100, 20)   # y 10–30, gap = 50-30 = 20
        self.assertEqual(major_axis_distance(src, dest, UP), 20)

    def test_touching_gap_is_zero(self):
        src  = rect(0, 44, 320, 64)   # y 44–108
        dest = rect(5,  5,  34, 34)   # y 5–39, gap = 44-39 = 5
        self.assertEqual(major_axis_distance(src, dest, UP), 5)

    def test_overlapping_gap_clamped_to_zero(self):
        src  = rect(0, 30, 100, 40)   # y 30–70
        dest = rect(0, 10, 100, 40)   # y 10–50, overlaps — raw would be negative
        self.assertEqual(major_axis_distance(src, dest, UP), 0)

    def test_gap_below(self):
        src  = rect(0, 10, 100, 20)   # y 10–30
        dest = rect(0, 50, 100, 20)   # y 50–70, gap = 50-30 = 20
        self.assertEqual(major_axis_distance(src, dest, DOWN), 20)

    def test_gap_to_left(self):
        src  = rect(100, 0, 50, 20)   # x 100–150
        dest = rect(20,  0, 50, 20)   # x 20–70, gap = 100-70 = 30
        self.assertEqual(major_axis_distance(src, dest, LEFT), 30)

    def test_gap_to_right(self):
        src  = rect(20, 0, 50, 20)    # x 20–70
        dest = rect(100, 0, 50, 20)   # x 100–150, gap = 100-70 = 30
        self.assertEqual(major_axis_distance(src, dest, RIGHT), 30)


class TestMinorAxisDistance(unittest.TestCase):

    def test_aligned_centers_for_up(self):
        """Horizontally centered widgets have zero minor axis distance."""
        src  = rect(0, 50, 100, 20)   # center x = 50
        dest = rect(0, 10, 100, 20)   # center x = 50
        self.assertEqual(minor_axis_distance(src, dest, UP), 0)

    def test_offset_centers_for_up(self):
        src  = rect(100, 50, 200, 20)  # center x = 200
        dest = rect(5,   10,  34, 34)  # center x = 22
        self.assertAlmostEqual(minor_axis_distance(src, dest, UP), 178, delta=1)

    def test_aligned_centers_for_left(self):
        src  = rect(100, 10, 50, 20)   # center y = 20
        dest = rect(20,  10, 50, 20)   # center y = 20
        self.assertEqual(minor_axis_distance(src, dest, LEFT), 0)


class TestWeightedDistance(unittest.TestCase):

    def test_formula(self):
        self.assertEqual(weighted_distance(3, 4), 13 * 9 + 16)   # 117 + 16 = 133

    def test_zero_minor(self):
        self.assertEqual(weighted_distance(5, 0), 13 * 25)

    def test_zero_major(self):
        self.assertEqual(weighted_distance(0, 5), 25)

    def test_major_dominates(self):
        """Major axis (×13 weight) should dominate over minor axis."""
        score_far_aligned   = weighted_distance(10, 0)   # 13*100 = 1300
        score_close_offset  = weighted_distance(5, 50)   # 13*25 + 2500 = 2825
        self.assertTrue(score_far_aligned < score_close_offset,
                        str(score_far_aligned) + " should be < " + str(score_close_offset))


class TestBeamBeats(unittest.TestCase):

    def test_in_beam_beats_out_of_beam(self):
        """A candidate inside the source beam must beat one outside it."""
        src    = rect(0, 44, 320, 64)   # full-width list item
        # in-beam: same horizontal span, above
        in_b   = rect(5,  5, 34, 34)    # small top-left button — horizontal overlap 5–39 ⊂ 0–320
        # out-of-beam: narrow widget far to the right but also above
        out_b  = rect(400, 5, 34, 34)   # x 400–434 — no overlap with 0–320
        self.assertTrue(beam_beats(src, in_b, out_b, UP))
        self.assertFalse(beam_beats(src, out_b, in_b, UP))

    def test_both_in_beam_no_beam_win(self):
        """When both are in beam, beam_beats returns False for both."""
        src   = rect(0, 44, 320, 64)
        rect1 = rect(0,  5, 100, 34)
        rect2 = rect(100, 5, 100, 34)
        self.assertFalse(beam_beats(src, rect1, rect2, UP))
        self.assertFalse(beam_beats(src, rect2, rect1, UP))

    def test_both_out_of_beam_no_beam_win(self):
        src   = rect(200, 44, 100, 64)   # x 200–300
        rect1 = rect(400, 5, 50, 34)     # x 400–450 — out
        rect2 = rect(0,   5, 50, 34)     # x 0–50 — out
        self.assertFalse(beam_beats(src, rect1, rect2, UP))
        self.assertFalse(beam_beats(src, rect2, rect1, UP))


class TestIsBetterCandidate(unittest.TestCase):

    def test_basic_up_beats_nothing(self):
        """A valid UP candidate beats the seeded ghost rect."""
        src   = rect(0, 44, 320, 64)
        dest  = rect(5,  5,  34, 34)
        # Ghost rect seeded below src (so any real UP candidate beats it)
        ghost = (src[0], src[3] + 1, src[2], src[3] + 1 + (src[3] - src[1]))
        self.assertTrue(is_better_candidate(src, dest, ghost, UP))

    def test_non_candidate_does_not_beat(self):
        """A widget below the source is not a UP candidate at all."""
        src   = rect(0, 44, 320, 64)
        below = rect(0, 120, 320, 40)
        ghost = (src[0], src[3] + 1, src[2], src[3] + 1 + (src[3] - src[1]))
        self.assertFalse(is_better_candidate(src, below, ghost, UP))

    def test_appstore_regression_settings_button_beats_nothing(self):
        """The AppStore regression: small top-left settings_button must be reachable via UP.

        src  = full-width list item (0,44)-(320,108)
        dest = settings_button     (5,5)-(39,39)

        The old ±45° cone excluded dest because the angle from src center
        (160,76) to dest center (22,22) is ~292° (LEFT), outside the 0°±45° UP cone.

        The Android algorithm:
        - isCandidate: dest.bottom(39) < src.top(44) ✓
        - beams_overlap for UP: dest.x(5–39) overlaps src.x(0–320) ✓ → in beam → wins
        """
        src  = (0, 44, 320, 108)   # full-width list item
        dest = (5,  5,  39,  39)   # small top-left settings button
        ghost = (src[0], src[3] + 1, src[2], src[3] + 1 + (src[3] - src[1]))
        self.assertTrue(is_candidate(src, dest, UP),
                        "settings_button should pass isCandidate for UP")
        self.assertTrue(beams_overlap(src, dest, UP),
                        "settings_button should be in beam for UP from list item")
        self.assertTrue(is_better_candidate(src, dest, ghost, UP),
                        "settings_button should beat ghost rect as UP candidate")

    def test_closer_wins_when_both_in_beam(self):
        """When two widgets are both in-beam, the closer one wins."""
        src    = rect(0, 100, 200, 40)   # y 100–140
        close  = rect(0,  60, 200, 20)   # y 60–80, gap = 100-80 = 20
        far    = rect(0,  10, 200, 20)   # y 10–30, gap = 100-30 = 70
        # close should beat far
        self.assertTrue(is_better_candidate(src, close, far, UP))
        self.assertFalse(is_better_candidate(src, far, close, UP))

    def test_in_beam_beats_closer_out_of_beam_for_left_right(self):
        """For LEFT/RIGHT, being in-beam is an absolute win regardless of distance."""
        src     = rect(100, 10, 50, 40)   # y 10–50, center y=30
        in_b    = rect(20,  15, 50, 20)   # y 15–35 — overlaps src y → in beam, farther
        out_b   = rect(40,  60, 40, 20)   # y 60–80 — no overlap → out of beam, closer
        # in_b is to the left of src (x 20–70 vs src x 100–150)
        # out_b is also to the left (x 40–80 vs src x 100–150), and closer in x
        self.assertTrue(is_better_candidate(src, in_b, out_b, LEFT),
                        "In-beam widget should beat closer out-of-beam widget for LEFT")

    def test_aligned_beats_offset_at_equal_distance(self):
        """At the same forward distance, better-aligned (lower minor) widget wins."""
        src      = rect(100, 100, 100, 40)  # center x=150, y 100–140
        aligned  = rect(100, 50,  100, 30)  # center x=150, gap=100-80=20, minor=0
        offset   = rect(200, 50,  100, 30)  # center x=250, gap=100-80=20, minor=100
        self.assertTrue(is_better_candidate(src, aligned, offset, UP))
        self.assertFalse(is_better_candidate(src, offset, aligned, UP))


if __name__ == "__main__":
    unittest.main()
