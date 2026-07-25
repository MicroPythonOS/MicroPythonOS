import unittest
from mpos.partitions import get_next_update_partition


class MockPartitionInfo:
    def __init__(self, label):
        self._label = label

    def info(self):
        return ("app", "factory", 0x10000, 0x100000, self._label, True)


class MockPartition:
    TYPE_APP = 0
    RUNNING = "running"

    _current_label = "ota_0"
    _labels = {"ota_0": True, "ota_1": True}

    @classmethod
    def set_current(cls, label):
        cls._current_label = label

    @classmethod
    def set_labels(cls, labels):
        cls._labels = dict(labels)

    class find_result:
        pass

    def __init__(self, subtype=None):
        self.subtype = subtype

    def info(self):
        return ("app", "factory", 0x10000, 0x100000, self._current_label, True)

    @classmethod
    def find(cls, type, label=None):
        if label not in cls._labels or not cls._labels[label]:
            return []
        result = cls.find_result()
        result.label = label
        return [result]

    @classmethod
    def reset(cls):
        cls._current_label = "ota_0"
        cls._labels = {"ota_0": True, "ota_1": True}


class TestGetNextUpdatePartition(unittest.TestCase):

    def setUp(self):
        MockPartition.reset()
        MockPartition._current_label = "ota_0"

    def test_ota_0_to_ota_1(self):
        MockPartition._current_label = "ota_0"
        result = get_next_update_partition(partition_module=MockPartition)
        self.assertEqual(result.label, "ota_1")

    def test_ota_1_to_ota_0(self):
        MockPartition._current_label = "ota_1"
        result = get_next_update_partition(partition_module=MockPartition)
        self.assertEqual(result.label, "ota_0")

    def test_missing_ota_1(self):
        MockPartition._current_label = "ota_0"
        MockPartition._labels = {"ota_0": True, "ota_1": False}
        with self.assertRaises(Exception) as ctx:
            get_next_update_partition(partition_module=MockPartition)
        self.assertIn("ota_1", str(ctx.exception))

    def test_missing_ota_0(self):
        MockPartition._current_label = "ota_1"
        MockPartition._labels = {"ota_0": False, "ota_1": True}
        with self.assertRaises(Exception) as ctx:
            get_next_update_partition(partition_module=MockPartition)
        self.assertIn("ota_0", str(ctx.exception))

    def test_unknown_current_goes_to_ota_1(self):
        MockPartition._current_label = "factory"
        result = get_next_update_partition(partition_module=MockPartition)
        self.assertEqual(result.label, "ota_1")

