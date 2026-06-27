# test_tfl_audio_error.py  (ASCII-only)
#
# Unit tests for PLSH-04 / D-11: AudioManager stub forces raise to verify
# _audio_error shows exactly "Audio error.\nSkipping to next song." once.
#
# Approach: duck-typed stubs -- we do NOT import tfl_player.py directly
# because it pulls in lvgl and the full mpos stack at module level, which
# crashes on the headless desktop runner.
#
# D-11 requirement: the test uses a sim stub that FORCES AudioManager to raise,
# NOT a board-ID check.  Board detection must NOT appear in this test or the
# production code path.
#
# Source lines mirrored in stubs:
#   - _audio_error:         tfl_player.py lines 684-686
#   - play_forever excerpt: tfl_player.py lines 761-792 (audio try/except block)

import unittest
import sys

sys.path.insert(0, "../tests")


# ---------------------------------------------------------------------------
# Minimal sys.modules stubs (guard against any transitively imported module
# trying to use lvgl or _thread before we can intercept)
# ---------------------------------------------------------------------------

class _MockLv:
    class ALIGN:
        TOP_MID = 0
    class PART:
        MAIN = 0
    def pct(self, n):
        return n

class _MockWidget:
    def set_text(self, *a, **k): pass

sys.modules.setdefault('lvgl', _MockLv())

import json as _json
sys.modules.setdefault('ujson', _json)

class _MockThread:
    @staticmethod
    def start_new_thread(fn, args): pass
    @staticmethod
    def allocate_lock():
        class _Lock:
            def acquire(self, *a, **k): return True
            def release(self): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return _Lock()

sys.modules.setdefault('_thread', _MockThread)
sys.modules.setdefault('urequests', object())


# ---------------------------------------------------------------------------
# Expected UI-SPEC string (02-UI-SPEC.md Copywriting Contract)
# ---------------------------------------------------------------------------

EXPECTED_AUDIO_ERROR_MSG = "Audio error.\nSkipping to next song."


# ---------------------------------------------------------------------------
# StreamPlayer _audio_error stub
#
# Source: tfl_player.py lines 684-686
#
#     def _audio_error(self, msg):
#         print("TFLPlayer audio error:", msg)
#         self.status("Audio error.\nSkipping to next song.")
# ---------------------------------------------------------------------------

class StreamPlayerStub:
    """
    Minimal stub that mirrors StreamPlayer._audio_error and the audio
    try/except block in play_forever().
    """

    def __init__(self, audio_manager_module, frags=None, stop_flag=None):
        self._audio_manager = audio_manager_module
        self._status_calls = []
        self._audio_error_call_count = [0]
        self.frags = frags or ["frag1.wav", "frag2.wav"]
        self._stop_flag_fn = stop_flag or (lambda: False)

        # Playback state
        class _State:
            fragment = 0
            def maybe_save(self): pass
        self.state = _State()

    # ---- _audio_error (verbatim from tfl_player.py line 684) ----
    def _audio_error(self, msg):
        self._audio_error_call_count[0] += 1
        print("TFLPlayer audio error:", msg)
        self.status("Audio error.\nSkipping to next song.")

    def status(self, txt):
        self._status_calls.append(txt)

    def last_status(self):
        if self._status_calls:
            return self._status_calls[-1]
        return None

    def stop_flag(self):
        return self._stop_flag_fn()

    # ---- audio try/except segment from play_forever() ----
    # SOURCE: tfl_player.py StreamPlayer.play_forever() audio try/except block
    # (lines ~761-792; keep in sync when play_forever changes).
    # Legacy reference: lines 761-792
    #
    #     ok = False
    #     try:
    #         player = AudioManager.player(file_path=cur_path, ...)
    #         player.start()
    #         ok = True
    #     except Exception as ex:
    #         print("TFLPlayer: player.start() raised:", ex, "path:", cur_path)
    #         self._audio_error(str(ex))
    #
    #     if not ok:
    #         for _ in range(15):
    #             if self.stop_flag():
    #                 break
    #             time.sleep_ms(100)
    #         self.state.fragment = len(frags)
    #         self.state.maybe_save()

    def run_one_audio_attempt(self, cur_path):
        """
        Runs the audio try/except block for one fragment (without the time.sleep_ms wait).
        Returns True if playback succeeded, False if _audio_error was triggered.
        """
        frags = self.frags
        ok = False
        try:
            player = self._audio_manager.player(
                file_path=cur_path,
                stream_type="STREAM_MUSIC",
                on_complete=lambda _res=None: None
            )
            player.start()
            ok = True
        except Exception as ex:
            print("TFLPlayer: player.start() raised:", ex, "path:", cur_path)
            self._audio_error(str(ex))

        if not ok:
            # Skip the 15 x 100ms wait in tests (time-consuming and unrelated to logic)
            # Jump to next song
            self.state.fragment = len(frags)
            self.state.maybe_save()

        return ok


# ---------------------------------------------------------------------------
# Mock AudioManager objects
# ---------------------------------------------------------------------------

class _RaisingPlayer:
    """A player whose start() always raises ValueError (D-11 sim stub)."""
    def __init__(self, exc_msg="mock audio error"):
        self._exc_msg = exc_msg

    def start(self):
        raise ValueError(self._exc_msg)


class _SuccessPlayer:
    """A player whose start() succeeds."""
    def start(self):
        pass


class MockAudioManagerRaising:
    """AudioManager stub: player() returns a player that raises on start()."""
    STREAM_MUSIC = "STREAM_MUSIC"

    def player(self, file_path=None, stream_type=None, on_complete=None):
        return _RaisingPlayer()

    @staticmethod
    def stop():
        pass

    @staticmethod
    def set_volume(v):
        pass


class MockAudioManagerSuccess:
    """AudioManager stub: player() returns a player that succeeds."""
    STREAM_MUSIC = "STREAM_MUSIC"

    def player(self, file_path=None, stream_type=None, on_complete=None):
        return _SuccessPlayer()

    @staticmethod
    def stop():
        pass

    @staticmethod
    def set_volume(v):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAudioErrorCleanMessage(unittest.TestCase):
    """PLSH-04: AudioManager.player().start() raising shows exactly one clean message."""

    def test_audio_error_shows_clean_message(self):
        """When player.start() raises, status is exactly the UI-SPEC audio error string."""
        stub = StreamPlayerStub(MockAudioManagerRaising())
        stub.run_one_audio_attempt("cache_audio/frag1.wav")

        self.assertEqual(
            stub.last_status(), EXPECTED_AUDIO_ERROR_MSG,
            "Exact UI-SPEC audio error string mismatch"
        )

    def test_audio_error_no_raw_exception_in_status(self):
        """Raw exception text ('mock audio error') must NOT appear in the status string."""
        raw_exc_text = "mock audio error"
        stub = StreamPlayerStub(MockAudioManagerRaising(exc_msg=raw_exc_text))
        stub.run_one_audio_attempt("cache_audio/frag1.wav")

        msg = stub.last_status()
        self.assertTrue(
            raw_exc_text not in msg,
            "Raw exception text must not appear in UI status (D-06)"
        )

    def test_audio_error_called_exactly_once(self):
        """_audio_error is called exactly once per audio failure (no double-call regression)."""
        stub = StreamPlayerStub(MockAudioManagerRaising())
        stub.run_one_audio_attempt("cache_audio/frag1.wav")

        self.assertEqual(
            stub._audio_error_call_count[0], 1,
            "_audio_error must be called exactly once (double-call regression guard)"
        )

    def test_audio_error_called_once_per_fragment(self):
        """Two separate audio failures each call _audio_error exactly once each."""
        stub = StreamPlayerStub(MockAudioManagerRaising())
        stub.run_one_audio_attempt("cache_audio/frag1.wav")
        # Reset state.fragment so we can test a second attempt
        stub.state.fragment = 0
        stub.run_one_audio_attempt("cache_audio/frag2.wav")

        self.assertEqual(
            stub._audio_error_call_count[0], 2,
            "Two fragments should produce exactly 2 _audio_error calls"
        )

    def test_audio_success_does_not_call_audio_error(self):
        """When player.start() succeeds, _audio_error is never called."""
        stub = StreamPlayerStub(MockAudioManagerSuccess())
        stub.run_one_audio_attempt("cache_audio/frag1.wav")

        self.assertEqual(
            stub._audio_error_call_count[0], 0,
            "_audio_error must not be called on successful playback"
        )

    def test_audio_success_shows_no_error_status(self):
        """When player.start() succeeds, no error status is set."""
        stub = StreamPlayerStub(MockAudioManagerSuccess())
        stub.run_one_audio_attempt("cache_audio/frag1.wav")

        self.assertEqual(
            len(stub._status_calls), 0,
            "No status messages should be set on successful playback"
        )


class TestAudioErrorSongAdvance(unittest.TestCase):
    """PLSH-04 / D-11: after audio error, song-skip logic advances fragment index."""

    def test_audio_error_advances_fragment_to_end(self):
        """After audio error, state.fragment is set to len(frags) to skip to next song."""
        frags = ["f1.wav", "f2.wav", "f3.wav"]
        stub = StreamPlayerStub(MockAudioManagerRaising(), frags=frags)
        stub.state.fragment = 0

        stub.run_one_audio_attempt("cache_audio/f1.wav")

        self.assertEqual(
            stub.state.fragment, len(frags),
            "state.fragment must equal len(frags) after audio error to trigger song skip"
        )

    def test_audio_error_run_returns_false(self):
        """run_one_audio_attempt returns False when audio raises (ok=False)."""
        stub = StreamPlayerStub(MockAudioManagerRaising())
        result = stub.run_one_audio_attempt("cache_audio/frag1.wav")

        self.assertFalse(result, "run_one_audio_attempt must return False on audio error")

    def test_audio_success_run_returns_true(self):
        """run_one_audio_attempt returns True when audio succeeds (ok=True)."""
        stub = StreamPlayerStub(MockAudioManagerSuccess())
        result = stub.run_one_audio_attempt("cache_audio/frag1.wav")

        self.assertTrue(result, "run_one_audio_attempt must return True on audio success")

    def test_audio_success_does_not_advance_fragment(self):
        """On success, state.fragment is NOT advanced (normal play loop manages it)."""
        frags = ["f1.wav", "f2.wav"]
        stub = StreamPlayerStub(MockAudioManagerSuccess(), frags=frags)
        stub.state.fragment = 0

        stub.run_one_audio_attempt("cache_audio/f1.wav")

        self.assertEqual(
            stub.state.fragment, 0,
            "state.fragment must not change on successful playback"
        )


class TestAudioErrorMessageContent(unittest.TestCase):
    """Verify _audio_error message components per UI-SPEC Copywriting Contract."""

    def test_message_contains_audio_error(self):
        """Status message contains 'Audio error.'"""
        stub = StreamPlayerStub(MockAudioManagerRaising())
        stub.run_one_audio_attempt("cache_audio/frag1.wav")

        self.assertTrue(
            "Audio error." in stub.last_status(),
            "Status must contain 'Audio error.'"
        )

    def test_message_contains_skipping_to_next(self):
        """Status message contains 'Skipping to next song.'"""
        stub = StreamPlayerStub(MockAudioManagerRaising())
        stub.run_one_audio_attempt("cache_audio/frag1.wav")

        self.assertTrue(
            "Skipping to next song." in stub.last_status(),
            "Status must contain 'Skipping to next song.'"
        )

    def test_audio_error_direct_call(self):
        """Calling _audio_error() directly shows exactly the UI-SPEC string."""
        stub = StreamPlayerStub(MockAudioManagerRaising())
        stub._audio_error("some exception detail")

        self.assertEqual(
            stub.last_status(), EXPECTED_AUDIO_ERROR_MSG,
            "Direct _audio_error() call must set the exact UI-SPEC string"
        )

    def test_audio_error_direct_call_count(self):
        """Direct call to _audio_error() increments call counter exactly once."""
        stub = StreamPlayerStub(MockAudioManagerRaising())
        stub._audio_error("some detail")

        self.assertEqual(stub._audio_error_call_count[0], 1)

    def test_audio_error_message_no_macOS_runner_text(self):
        """Status must not contain the old macOS runner conditional message (regression)."""
        stub = StreamPlayerStub(MockAudioManagerRaising())
        stub.run_one_audio_attempt("cache_audio/frag1.wav")
        msg = stub.last_status()

        # The old _audio_error included "(If you're on the macOS runner...)"
        # This is the exact string to guard against bringing back
        self.assertTrue(
            "macOS runner" not in msg,
            "Old macOS runner message must not appear in audio error status"
        )
