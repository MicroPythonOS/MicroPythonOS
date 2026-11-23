import unittest

from mpos.zipasset import ZipAssetError, entries, entry_size, load

FIXTURES = "../tests/zipasset"
PAYLOAD = bytes((i * 13 + 7) & 0xFF for i in range(20000))


class TestZipAsset(unittest.TestCase):
    def test_lists_entries(self):
        self.assertEqual(entries(FIXTURES + "/asset_deflated.zip"), ["doom1.wad"])

    def test_reports_the_declared_size_without_inflating(self):
        self.assertEqual(entry_size(FIXTURES + "/asset_deflated.zip"), len(PAYLOAD))
        self.assertEqual(entry_size(FIXTURES + "/asset_deflated.zip", "doom1.wad"),
                         len(PAYLOAD))
        self.assertEqual(entry_size(FIXTURES + "/asset_deflated.zip", "nope"), 0)
        self.assertEqual(entry_size(FIXTURES + "/does-not-exist.zip"), 0)

    def test_loads_stored_entry(self):
        buffer, size = load(FIXTURES + "/asset_stored.zip")
        self.assertEqual(size, len(PAYLOAD))
        self.assertEqual(buffer, PAYLOAD)

    def test_loads_deflated_entry(self):
        buffer, size = load(FIXTURES + "/asset_deflated.zip", "doom1.wad")
        self.assertEqual(size, len(PAYLOAD))
        self.assertEqual(buffer, PAYLOAD)

    def test_progress_reaches_the_end(self):
        seen = []

        def progress(done, total):
            seen.append((done, total))

        load(FIXTURES + "/asset_deflated.zip", progress=progress)
        self.assertEqual(seen[-1][0], len(PAYLOAD))
        self.assertEqual(seen[-1][1], len(PAYLOAD))

    def test_loads_into_a_caller_supplied_buffer(self):
        # A host that keeps the asset in C-heap memory (mpos_core.buffer)
        # hands the buffer over; it must be filled in place, not replaced.
        supplied = bytearray(len(PAYLOAD))
        buffer, size = load(FIXTURES + "/asset_deflated.zip",
                            buffer=supplied)
        self.assertIs(buffer, supplied)
        self.assertEqual(size, len(PAYLOAD))
        self.assertEqual(bytes(buffer), PAYLOAD)

    def test_a_wrong_sized_buffer_is_refused(self):
        with self.assertRaises(ZipAssetError):
            load(FIXTURES + "/asset_deflated.zip",
                 buffer=bytearray(len(PAYLOAD) - 1))
        with self.assertRaises(ZipAssetError):
            load(FIXTURES + "/asset_deflated.zip",
                 buffer=bytearray(len(PAYLOAD) + 1))

    def test_missing_entry_raises(self):
        with self.assertRaises(ZipAssetError):
            load(FIXTURES + "/asset_deflated.zip", "nope.wad")

    def test_missing_file_raises(self):
        with self.assertRaises(ZipAssetError):
            load(FIXTURES + "/does-not-exist.zip")

    def test_corrupt_entry_raises(self):
        with self.assertRaises(ZipAssetError):
            load(FIXTURES + "/asset_corrupt.zip")


if __name__ == "__main__":
    unittest.main()
