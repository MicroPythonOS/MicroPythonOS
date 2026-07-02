# secp256k1_compat.py: Compatibility layer for secp256k1.py to use MicroPython's usecp256k1 module

import usecp256k1

# Constants (from libsecp256k1)
SECP256K1_CONTEXT_SIGN = 1 << 8  # 256
SECP256K1_CONTEXT_VERIFY = 1 << 9  # 512
SECP256K1_EC_COMPRESSED = 1 << 1  # 2
SECP256K1_EC_UNCOMPRESSED = 0

# Dummy CData class to mimic cffi's CData
class CData:
    def __init__(self, data, type_str):
        self._data = data
        self._type = type_str

    def __str__(self):
        # Return a readable string with type and hex data
        if isinstance(self._data, (bytes, bytearray)):
            return f"{self._type}: {self._data.hex()}"
        elif isinstance(self._data, list):
            return f"{self._type}: {bytes(self._data).hex()}"
        return f"{self._type}: {self._data}"

    def __repr__(self):
        # More detailed representation, similar to __str__ but with memory address
        return f"<CData {self._type} at {hex(id(self))}, data={self._data.hex() if isinstance(self._data, (bytes, bytearray)) else self._data}>"

# Dummy ffi class to mimic cffi
class FFI:
    NULL = None  # Mimic cffi's NULL pointer
    CData = CData  # Expose CData class

    def __init__(self):
        # Cache type strings for identity comparison
        self._types = {
            'secp256k1_pubkey *': 'secp256k1_pubkey *',
            'secp256k1_ecdsa_signature *': 'secp256k1_ecdsa_signature *',
            'secp256k1_ecdsa_recoverable_signature *': 'secp256k1_ecdsa_recoverable_signature *',
            'secp256k1_xonly_pubkey *': 'secp256k1_xonly_pubkey *',
            'secp256k1_keypair *': 'secp256k1_keypair *',
        }

    def new(self, type_str, init=None):
        if 'char' in type_str:
            size = int(type_str.split('[')[1].rstrip(']'))
            return CData(bytearray(size), type_str)
        elif 'size_t *' in type_str:
            data = [init if init is not None else 0]
            return CData(data, type_str)
        elif type_str == 'secp256k1_pubkey *':
            return CData(bytearray(64), type_str)
        elif type_str == 'secp256k1_ecdsa_signature *':
            return CData(bytearray(64), type_str)
        elif type_str == 'secp256k1_ecdsa_recoverable_signature *':
            return CData(bytearray(65), type_str)
        elif type_str == 'secp256k1_xonly_pubkey *':
            return CData(bytearray(32), type_str)
        elif type_str == 'secp256k1_keypair *':
            return CData(bytearray(96), type_str)
        raise ValueError(f"Unsupported ffi type: {type_str}")

    def buffer(self, obj, size=None):
        if isinstance(obj, CData):
            obj = obj._data
        if isinstance(obj, list):
            return bytes(obj)
        return bytes(obj[:size] if size is not None else obj)

    def memmove(self, dst, src, n):
        if isinstance(dst, CData):
            dst = dst._data
        if isinstance(src, CData):
            src = src._data
        if isinstance(src, bytes):
            src = bytearray(src)
        dst[:n] = src[:n]

    def callback(self, signature):
        def decorator(func):
            return func
        return decorator

    def typeof(self, obj):
        if isinstance(obj, CData):
            return self._types.get(obj._type, obj._type)
        if isinstance(obj, str):
            return self._types.get(obj, obj)
        raise TypeError("Object is not a CData instance or type string")

# Dummy lib class to map to usecp256k1 functions
class Lib:
    SECP256K1_EC_COMPRESSED = SECP256K1_EC_COMPRESSED
    SECP256K1_EC_UNCOMPRESSED = SECP256K1_EC_UNCOMPRESSED
    SECP256K1_CONTEXT_SIGN = SECP256K1_CONTEXT_SIGN
    SECP256K1_CONTEXT_VERIFY = SECP256K1_CONTEXT_VERIFY

    def secp256k1_context_create(self, flags):
        return object()

    def secp256k1_ec_seckey_verify(self, ctx, seckey):
        try:
            return usecp256k1.ec_seckey_verify(seckey)
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_signature_serialize_der(self, ctx, output, outputlen, raw_sig):
        try:
            if isinstance(raw_sig, FFI.CData):
                raw_sig = raw_sig._data
            if isinstance(output, FFI.CData):
                output = output._data
            if isinstance(outputlen, FFI.CData):
                outputlen = outputlen._data
            result = usecp256k1.ecdsa_signature_serialize_der(raw_sig)
            if result is None:
                return 0
            output[:len(result)] = result
            outputlen[0] = len(result)
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_signature_parse_der(self, ctx, raw_sig, ser_sig, ser_len):
        try:
            if isinstance(raw_sig, FFI.CData):
                raw_sig = raw_sig._data
            result = usecp256k1.ecdsa_signature_parse_der(ser_sig)
            if result is None:
                return 0
            raw_sig[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_signature_serialize_compact(self, ctx, output, raw_sig):
        try:
            if isinstance(raw_sig, FFI.CData):
                raw_sig = raw_sig._data
            if isinstance(output, FFI.CData):
                output = output._data
            result = usecp256k1.ecdsa_signature_serialize_compact(raw_sig)
            if result is None:
                return 0
            output[:64] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_signature_parse_compact(self, ctx, raw_sig, ser_sig):
        try:
            if isinstance(raw_sig, FFI.CData):
                raw_sig = raw_sig._data
            result = usecp256k1.ecdsa_signature_parse_compact(ser_sig)
            if result is None:
                return 0
            raw_sig[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_signature_normalize(self, ctx, sigout, raw_sig):
        try:
            if isinstance(raw_sig, FFI.CData):
                raw_sig = raw_sig._data
            if sigout != FFI.NULL:
                if isinstance(sigout, FFI.CData):
                    sigout = sigout._data
            is_normalized = usecp256k1.ecdsa_signature_normalize(raw_sig)
            if sigout != FFI.NULL:
                sigout[:] = is_normalized[1] if is_normalized[1] else raw_sig
            return is_normalized[0]
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_sign(self, ctx, raw_sig, msg32, privkey, nonce_fn, nonce_data):
        try:
            if isinstance(raw_sig, FFI.CData):
                raw_sig = raw_sig._data
            result = usecp256k1.ecdsa_sign(msg32, privkey)
            if result is None:
                return 0
            raw_sig[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_verify(self, ctx, raw_sig, msg32, pubkey):
        try:
            if isinstance(raw_sig, FFI.CData):
                raw_sig = raw_sig._data
            if isinstance(pubkey, FFI.CData):
                pubkey = pubkey._data
            return usecp256k1.ecdsa_verify(raw_sig, msg32, pubkey)
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_recoverable_signature_serialize_compact(self, ctx, output, recid, recover_sig):
        try:
            if isinstance(recover_sig, FFI.CData):
                recover_sig = recover_sig._data
            if isinstance(output, FFI.CData):
                output = output._data
            if isinstance(recid, FFI.CData):
                recid = recid._data
            result, rec_id = usecp256k1.ecdsa_sign_recoverable(recover_sig)
            if result is None:
                return 0
            output[:64] = result
            recid[0] = rec_id
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_recoverable_signature_parse_compact(self, ctx, recover_sig, ser_sig, rec_id):
        try:
            if isinstance(recover_sig, FFI.CData):
                recover_sig = recover_sig._data
            result = usecp256k1.ecdsa_sign_recoverable(ser_sig, rec_id)
            if result is None:
                return 0
            recover_sig[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_recoverable_signature_convert(self, ctx, normal_sig, recover_sig):
        try:
            if isinstance(normal_sig, FFI.CData):
                normal_sig = normal_sig._data
            if isinstance(recover_sig, FFI.CData):
                recover_sig = recover_sig._data
            result = usecp256k1.ecdsa_sign_recoverable(recover_sig)
            if result is None:
                return 0
            normal_sig[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_sign_recoverable(self, ctx, raw_sig, msg32, privkey, nonce_fn, nonce_data):
        try:
            if isinstance(raw_sig, FFI.CData):
                raw_sig = raw_sig._data
            result = usecp256k1.ecdsa_sign_recoverable(msg32, privkey)
            if result is None:
                return 0
            raw_sig[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdsa_recover(self, ctx, pubkey, recover_sig, msg32):
        try:
            if isinstance(pubkey, FFI.CData):
                pubkey = pubkey._data
            if isinstance(recover_sig, FFI.CData):
                recover_sig = recover_sig._data
            result = usecp256k1.ecdsa_sign_recoverable(recover_sig, msg32)
            if result is None:
                return 0
            pubkey[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_schnorrsig_sign(self, ctx, sig64, msg, msg_len, keypair, aux_rand32):
        try:
            if isinstance(keypair, FFI.CData):
                keypair = keypair._data
            if isinstance(sig64, FFI.CData):
                sig64 = sig64._data
            result = usecp256k1.schnorrsig_sign(msg, keypair)
            if result is None:
                return 0
            sig64[:64] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_schnorrsig_verify(self, ctx, schnorr_sig, msg, msg_len, xonly_pubkey):
        try:
            if isinstance(xonly_pubkey, FFI.CData):
                xonly_pubkey = xonly_pubkey._data
            return usecp256k1.schnorrsig_verify(schnorr_sig, msg, xonly_pubkey)
        except (ValueError, AttributeError):
            print("WARNING: secp256k1_compat.py secp256k1_schnorrsig_verify error, returning 0")
            return 0

    def secp256k1_tagged_sha256(self, ctx, hash32, tag, tag_len, msg, msg_len):
        try:
            if isinstance(hash32, FFI.CData):
                hash32 = hash32._data
            result = usecp256k1.tagged_sha256(tag, msg)
            if result is None:
                return 0
            hash32[:32] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ec_pubkey_serialize(self, ctx, output, outlen, pubkey, flags):
        try:
            if isinstance(pubkey, FFI.CData):
                pubkey = pubkey._data
            if isinstance(output, FFI.CData):
                output = output._data
            if isinstance(outlen, FFI.CData):
                outlen = outlen._data
            result = usecp256k1.ec_pubkey_serialize(pubkey, flags)
            if result is None:
                return 0
            output[:len(result)] = result
            outlen[0] = len(result)
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ec_pubkey_parse(self, ctx, pubkey, pubkey_ser, ser_len):
        try:
            if isinstance(pubkey, FFI.CData):
                pubkey = pubkey._data
            result = usecp256k1.ec_pubkey_parse(pubkey_ser)
            if result is None:
                return 0
            pubkey[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ec_pubkey_combine(self, ctx, outpub, pubkeys, n_pubkeys):
        try:
            if isinstance(outpub, FFI.CData):
                outpub = outpub._data
            pubkeys_data = [pk._data if isinstance(pk, FFI.CData) else pk for pk in pubkeys]
            result = usecp256k1.ec_pubkey_combine(pubkeys_data)
            if result is None:
                return 0
            outpub[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ec_pubkey_tweak_add(self, ctx, pubkey, scalar):
        try:
            if isinstance(pubkey, FFI.CData):
                pubkey = pubkey._data
            result = usecp256k1.ec_pubkey_tweak_add(pubkey, scalar)
            if result is None:
                return 0
            pubkey[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ec_pubkey_tweak_mul(self, ctx, pubkey, scalar):
        try:
            if isinstance(pubkey, FFI.CData):
                pubkey = pubkey._data
            result = usecp256k1.ec_pubkey_tweak_mul(pubkey, scalar)
            if result is None:
                return 0
            pubkey[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ec_pubkey_create(self, ctx, pubkey, privkey):
        try:
            if isinstance(pubkey, FFI.CData):
                pubkey = pubkey._data
            result = usecp256k1.ec_pubkey_create(privkey)
            if result is None:
                return 0
            pubkey[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_xonly_pubkey_from_pubkey(self, ctx, xonly_pubkey, pk_parity, pubkey):
        try:
            if isinstance(xonly_pubkey, FFI.CData):
                xonly_pubkey = xonly_pubkey._data
            if isinstance(pubkey, FFI.CData):
                pubkey = pubkey._data
            if isinstance(pk_parity, FFI.CData):
                pk_parity = pk_parity._data
            result, parity = usecp256k1.xonly_pubkey_from_pubkey(pubkey)
            if result is None:
                return 0
            xonly_pubkey[:] = result
            if pk_parity != FFI.NULL:
                pk_parity[0] = parity
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ec_privkey_tweak_add(self, ctx, privkey, scalar):
        try:
            if isinstance(privkey, FFI.CData):
                privkey = privkey._data
            result = usecp256k1.ec_privkey_tweak_add(privkey, scalar)
            if result is None:
                return 0
            privkey[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ec_privkey_tweak_mul(self, ctx, privkey, scalar):
        try:
            if isinstance(privkey, FFI.CData):
                privkey = privkey._data
            result = usecp256k1.ec_privkey_tweak_mul(privkey, scalar)
            if result is None:
                return 0
            privkey[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_keypair_create(self, ctx, keypair, privkey):
        try:
            if isinstance(keypair, FFI.CData):
                keypair = keypair._data
            result = usecp256k1.keypair_create(privkey)
            if result is None:
                return 0
            keypair[:] = result
            return 1
        except (ValueError, AttributeError):
            return 0

    def secp256k1_ecdh(self, ctx, output, pubkey, seckey, hashfn=FFI.NULL, hasharg=FFI.NULL):
        try:
            if isinstance(pubkey, FFI.CData):
                pubkey = pubkey._data
            if isinstance(output, FFI.CData):
                output = output._data
            result = usecp256k1.ecdh(pubkey, seckey)
            if result is None:
                return 0
            output[:32] = result
            return 1
        except ValueError as e:
            print(f"secp256k1_compat.py secp256k1_ecdh got ValueError: {e}")
            return 0

# Instantiate ffi and lib
ffi = FFI()
lib = Lib()

# Feature flags
HAS_RECOVERABLE = hasattr(usecp256k1, 'ecdsa_sign_recoverable')
HAS_SCHNORR = hasattr(usecp256k1, 'schnorrsig_sign')
HAS_ECDH = hasattr(usecp256k1, 'ecdh')
HAS_EXTRAKEYS = hasattr(usecp256k1, 'keypair_create')

# Define copy_x for ECDH
def copy_x(output, x32, y32, data):
    ffi.memmove(output, x32, 32)
    return 1
