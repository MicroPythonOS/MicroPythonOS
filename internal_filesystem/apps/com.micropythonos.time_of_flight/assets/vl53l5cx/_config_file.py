# Copyright (c) 2021 Mark Grosen <mark@grosen.org>
#
# SPDX-License-Identifier: MIT

import sys
from os import stat


def _find_file(name, req_size):
    file = None
    size_on_disk = 0
    for d in sys.path:
        file = d + "/" + name
        try:
            size_on_disk = stat(file)[6]
            break
        except:
            file = None

    if file:
        if size_on_disk != req_size:
            raise ValueError("firmware file size incorrect")
    else:
        raise ValueError("could not find file: " + name)

    return file


class ConfigDataFile:
    _FW_SIZE = 0x15000
    _DEFAULT_CONFIG_OFFSET = _FW_SIZE
    _DEFAULT_CONFIG_SIZE = 972
    _XTALK_OFFSET = _FW_SIZE + _DEFAULT_CONFIG_SIZE
    _XTALK_SIZE = 776
    _XTALK4X4_OFFSET = _FW_SIZE + _DEFAULT_CONFIG_SIZE + _XTALK_SIZE
    _XTALK4X4_SIZE = 776

    def __init__(self, name="vl53l5cx/vl_fw_config.bin"):
        self._file_name = _find_file(name, 88540)

    def _read_offset_data(self, offset, size):
        with open(self._file_name, "rb") as fw_file:
            fw_file.seek(offset)
            return fw_file.read(size)

    @property
    def default_config_data(self):
        return self._read_offset_data(self._DEFAULT_CONFIG_OFFSET,
                                      self._DEFAULT_CONFIG_SIZE)

    @property
    def xtalk_data(self):
        return self._read_offset_data(self._XTALK_OFFSET,
                                      self._XTALK_SIZE)

    @property
    def xtalk4x4_data(self):
        return self._read_offset_data(self._XTALK4X4_OFFSET,
                                      self._XTALK4X4_SIZE)

    def fw_data(self, chunk_size=0x1000):
        with open(self._file_name, "rb") as fw_file:
            for _ in range(0, 0x15000, chunk_size):
                yield fw_file.read(chunk_size)
