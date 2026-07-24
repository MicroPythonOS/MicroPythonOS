# primitives.py: MicroPython compatibility layer for cryptography.hazmat.primitives.padding
# Implements PKCS7 padding and unpadding

def _byte_padding_check(block_size):
    if not (0 <= block_size <= 2040):
        raise ValueError("block_size must be in range(0, 2041).")
    if block_size % 8 != 0:
        raise ValueError("block_size must be a multiple of 8.")

class PKCS7PaddingContext:
    def __init__(self, block_size):
        _byte_padding_check(block_size)
        self.block_size = block_size // 8
        self._buffer = bytearray()

    def update(self, data):
        self._buffer.extend(data)
        block_size = self.block_size
        if len(self._buffer) >= block_size:
            to_return = self._buffer[:len(self._buffer) - (len(self._buffer) % block_size)]
            self._buffer = self._buffer[len(to_return):]
            #print(f"PKCS7PaddingContext.update returning: {to_return.hex()}")
            return to_return
        #print(f"PKCS7PaddingContext.update buffer: {self._buffer.hex()}")
        return b''

    def finalize(self):
        pad_length = self.block_size - (len(self._buffer) % self.block_size)
        padding = bytes([pad_length] * pad_length)
        self._buffer.extend(padding)
        result = bytes(self._buffer)
        #print(f"PKCS7PaddingContext.finalize pad_length: {pad_length}, padding: {padding.hex()}, result: {result.hex()}")
        self._buffer = bytearray()
        return result

class PKCS7UnpaddingContext:
    def __init__(self, block_size):
        _byte_padding_check(block_size)
        self.block_size = block_size // 8
        self._buffer = bytearray()

    def update(self, data):
        self._buffer.extend(data)
        #print(f"unpadder self._buffer is {self._buffer.hex()}")
        block_size = self.block_size
        # Return all complete blocks except the last one
        if len(self._buffer) >= block_size * 2:  # At least two blocks
            to_return = self._buffer[:len(self._buffer) - block_size]
            self._buffer = self._buffer[len(to_return):]
            #print(f"unpadder self._buffer is now {self._buffer.hex()} and returning {to_return.hex()}")
            return to_return
        #print(f"unpadder self._buffer retained: {self._buffer.hex()}")
        return b''

    def finalize(self):
        #print(f"unpadder finalize self._buffer: {self._buffer.hex()}")
        if not self._buffer or len(self._buffer) % self.block_size != 0:
            raise ValueError(f"Invalid padding A: buffer {self._buffer.hex()}, length {len(self._buffer)}, remainder {len(self._buffer) % self.block_size}")
        pad_length = self._buffer[-1]
        #print(f"unpadder finalize pad_length: {pad_length}, last {pad_length} bytes: {self._buffer[-pad_length:].hex()}")
        if pad_length > self.block_size or pad_length == 0:
            raise ValueError(f"Invalid padding B: pad_length {pad_length}")
        if self._buffer[-pad_length:] != bytes([pad_length] * pad_length):
            raise ValueError(f"Invalid padding C: expected {pad_length} bytes of {pad_length:02x}, got {self._buffer[-pad_length:].hex()}")
        result = bytes(self._buffer[:-pad_length])
        self._buffer = bytearray()
        #print(f"unpadder finalize result: {result.hex()}")
        return result

class PKCS7:
    def __init__(self, block_size):
        _byte_padding_check(block_size)
        self.block_size = block_size

    def padder(self):
        return PKCS7PaddingContext(self.block_size)

    def unpadder(self):
        return PKCS7UnpaddingContext(self.block_size)
