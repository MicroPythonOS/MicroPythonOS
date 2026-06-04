# secrets.py: Compatibility layer for CPython's secrets module in MicroPython
# Uses urandom for cryptographically secure randomness
# Implements SystemRandom, choice, randbelow, randbits, token_bytes, token_hex,
# token_urlsafe, and compare_digest

import urandom
import ubinascii

class SystemRandom:
    """Emulates random.SystemRandom using MicroPython's urandom."""
    
    def randrange(self, start, stop=None, step=1):
        """Return a random int in range(start, stop[, step])."""
        if stop is None:
            stop = start
            start = 0
        if step != 1:
            raise NotImplementedError("step != 1 not supported")
        if start >= stop:
            raise ValueError("empty range")
        range_size = stop - start
        return start + self._randbelow(range_size)
    
    def _randbelow(self, n):
        """Return a random int in [0, n)."""
        if n <= 0:
            raise ValueError("exclusive_upper_bound must be positive")
        k = (n.bit_length() + 7) // 8  # Bytes needed for n
        r = 0
        while True:
            r = int.from_bytes(self._getrandbytes(k), 'big')
            if r < n:
                return r
    
    def _getrandbytes(self, n):
        """Return n random bytes."""
        # Use bytes directly for compatibility with CPython secrets
        return bytes(urandom.getrandbits(8) for _ in range(n))
    
    def choice(self, seq):
        """Return a randomly chosen element from a non-empty sequence."""
        if not seq:
            raise IndexError("cannot choose from an empty sequence")
        return seq[self._randbelow(len(seq))]
    
    def randbits(self, k):
        """Return a non-negative int with k random bits."""
        if k < 0:
            raise ValueError("number of bits must be non-negative")
        numbytes = (k + 7) // 8
        return int.from_bytes(self._getrandbytes(numbytes), 'big') >> (numbytes * 8 - k)

# Instantiate SystemRandom for module-level functions
_sysrand = SystemRandom()

def choice(seq):
    """Return a randomly chosen element from a non-empty sequence."""
    return _sysrand.choice(seq)

def randbelow(exclusive_upper_bound):
    """Return a random int in [0, exclusive_upper_bound)."""
    return _sysrand._randbelow(exclusive_upper_bound)

def randbits(k):
    """Return a non-negative int with k random bits."""
    return _sysrand.randbits(k)

def token_bytes(nbytes=None):
    """Return a random byte string of nbytes. Default is 32 bytes."""
    if nbytes is None:
        nbytes = 32
    if nbytes < 0:
        raise ValueError("number of bytes must be non-negative")
    return _sysrand._getrandbytes(nbytes)

def token_hex(nbytes=None):
    """Return a random hex string of nbytes. Default is 32 bytes."""
    return ubinascii.hexlify(token_bytes(nbytes)).decode()

def token_urlsafe(nbytes=None):
    """Return a random URL-safe base64 string of nbytes. Default is 32 bytes."""
    if nbytes is None:
        nbytes = 32
    if nbytes < 0:
        raise ValueError("number of bytes must be non-negative")
    raw_bytes = token_bytes(nbytes)
    encoded = ubinascii.b2a_base64(raw_bytes).decode().rstrip('\n=')
    return encoded[:int(nbytes * 4 / 3)]

def compare_digest(a, b):
    """Return True if a and b are equal in constant time, else False."""
    if isinstance(a, str):
        a = a.encode()
    if isinstance(b, str):
        b = b.encode()
    if not isinstance(a, (bytes, bytearray)) or not isinstance(b, (bytes, bytearray)):
        raise TypeError("both inputs must be bytes-like or strings")
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= x ^ y
    return result == 0
