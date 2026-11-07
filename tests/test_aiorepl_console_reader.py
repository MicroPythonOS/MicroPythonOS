"""test_aiorepl_console_reader.py - Unit tests for the non-blocking console reader.

The asyncio REPL used to read the console with StreamReader(sys.stdin), which on
ESP32 ends up in a blocking, text-mode mp_hal_stdin_rx_chr(). A host program that
opens the USB-CDC port and writes bytes that are not a REPL session (device
detection probes: CBOR lead bytes such as 0xA6) leaves read(1) waiting for UTF-8
continuation bytes that never come, freezing every asyncio task on the device --
issue #297.

_StdinReader polls stdin and reads raw bytes, so a partial or invalid character
is abandoned instead of blocking the loop.

These tests are hardware-free: the poll object and the byte stream are fakes.
"""

import sys
import unittest

sys.path.insert(0, "../internal_filesystem/lib")

import asyncio
import time


class _FakePoll:
    def __init__(self, readable=True):
        self.readable = readable

    def poll(self, timeout=0):
        return [(0, 1)] if self.readable else []


class _FakeIn:
    def __init__(self, data, poll):
        self.data = data
        self.poll = poll

    def read(self, n=1):
        if not self.data:
            return b""
        out = self.data[:n]
        self.data = self.data[n:]
        if not self.data:
            self.poll.readable = False
        return out


class TestStdinReader(unittest.TestCase):

    def _reader(self, data, readable=True):
        import aiorepl

        poll = _FakePoll(readable)
        return aiorepl._StdinReader(poll=poll, stream=_FakeIn(data, poll)), poll

    def test_ascii_byte_returns_one_char(self):
        reader, _ = self._reader(b"a")
        self.assertEqual(asyncio.run(reader.read_char()), "a")

    def test_invalid_lead_byte_is_discarded_without_waiting(self):
        reader, _ = self._reader(b"\xa6")
        t0 = time.ticks_ms()
        got = asyncio.run(reader.read_char())
        elapsed = time.ticks_diff(time.ticks_ms(), t0)
        self.assertIsNone(got)
        self.assertTrue(elapsed < 50, "invalid byte waited %d ms" % elapsed)

    def test_split_utf8_sequence_is_decoded(self):
        reader, _ = self._reader(b"\xc3\xa9")
        self.assertEqual(asyncio.run(reader.read_char()), "\xe9")

    def test_incomplete_sequence_is_abandoned_after_timeout(self):
        reader, _ = self._reader(b"\xc3")
        t0 = time.ticks_ms()
        got = asyncio.run(reader.read_char())
        elapsed = time.ticks_diff(time.ticks_ms(), t0)
        self.assertIsNone(got, "incomplete sequence was not abandoned")
        self.assertTrue(
            elapsed >= reader.PARTIAL_TIMEOUT_MS,
            "abandoned after %d ms, before the %d ms timeout" % (elapsed, reader.PARTIAL_TIMEOUT_MS),
        )
        self.assertTrue(elapsed < 400, "abandon took %d ms" % elapsed)

    def test_carriage_return_is_normalised_to_newline(self):
        reader, _ = self._reader(b"\r")
        self.assertEqual(asyncio.run(reader.read_char()), "\n")

    def test_eof_returns_empty_string(self):
        reader, _ = self._reader(b"")
        self.assertEqual(asyncio.run(reader.read_char()), "")

    def test_no_byte_is_read_while_stdin_is_not_readable(self):
        stream = _FakeIn(b"b", _FakePoll(readable=False))
        import aiorepl

        reader = aiorepl._StdinReader(poll=stream.poll, stream=stream)

        async def main():
            task = asyncio.create_task(reader.read_char())
            await asyncio.sleep_ms(120)
            self.assertEqual(stream.data, b"b", "read from stdin without a poll hit")
            stream.poll.readable = True
            return await task

        self.assertEqual(asyncio.run(main()), "b")


if __name__ == "__main__":
    unittest.main()
