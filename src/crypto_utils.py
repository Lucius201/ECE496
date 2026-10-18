"""
Low-level cryptographic primitives used by the node.

Everything here is implemented with the Python standard library only:
  * secp256k1 elliptic-curve arithmetic (affine coordinates, double-and-add)
  * SHA-256 / double SHA-256 / RIPEMD-160 (hashlib, with a pycryptodome fallback)
  * Base58 / Base58Check encoding and decoding

Keeping the curve math visible (instead of hiding it behind a library) makes it
easy to explain exactly how a public key and address are derived.
"""

import hashlib

# --------------------------------------------------------------------------- #
# secp256k1 domain parameters (SEC 2, section 2.4.1)
#   y^2 = x^3 + 7  over the prime field F_p
# --------------------------------------------------------------------------- #
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F  # field prime
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141  # group order
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)

# The point at infinity (group identity) is represented as None.
INFINITY = None


def point_add(p1, p2):
    """Add two points on secp256k1 (affine coordinates)."""
    if p1 is INFINITY:
        return p2
    if p2 is INFINITY:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P == 0:          # P + (-P) = O
            return INFINITY
        # Point doubling: slope of the tangent line
        lam = (3 * x1 * x1) * pow(2 * y1, -1, P) % P
    else:
        # Point addition: slope of the secant line
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return (x3, y3)


def scalar_mult(k, point=G):
    """Compute k * point with the classic double-and-add algorithm."""
    if not 0 < k < N:
        raise ValueError("scalar out of range [1, N-1]")
    result = INFINITY
    addend = point
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


def is_on_curve(point):
    if point is INFINITY:
        return True
    x, y = point
    return (y * y - (x * x * x + 7)) % P == 0


def compress_pubkey(point):
    """SEC1 compressed encoding: 0x02/0x03 (parity of y) || 32-byte big-endian x."""
    x, y = point
    prefix = b"\x03" if y & 1 else b"\x02"
    return prefix + x.to_bytes(32, "big")


# --------------------------------------------------------------------------- #
# Hash functions
# --------------------------------------------------------------------------- #
def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def _make_ripemd160():
    # Some OpenSSL 3 builds disable RIPEMD-160 in hashlib ("legacy" provider).
    try:
        hashlib.new("ripemd160", b"")
        return lambda data: hashlib.new("ripemd160", data).digest()
    except (ValueError, TypeError):
        pass
    try:
        from Crypto.Hash import RIPEMD160  # pycryptodome

        return lambda data: RIPEMD160.new(data).digest()
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "RIPEMD-160 is not available in hashlib. Install pycryptodome: "
            "pip install pycryptodome"
        ) from exc


ripemd160 = _make_ripemd160()


def hash160(data: bytes) -> bytes:
    """RIPEMD160(SHA256(data)) - the 20-byte public key hash used by P2PKH."""
    return ripemd160(sha256(data))


# --------------------------------------------------------------------------- #
# Base58 / Base58Check
# Alphabet omits 0 (zero), O (capital o), I (capital i) and l (lower L).
# --------------------------------------------------------------------------- #
B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(B58_ALPHABET)}


def b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    chars = []
    while n:
        n, rem = divmod(n, 58)
        chars.append(B58_ALPHABET[rem])
    # Every leading 0x00 byte is encoded as a literal '1'
    leading_zeros = len(data) - len(data.lstrip(b"\x00"))
    return "1" * leading_zeros + "".join(reversed(chars))


def b58decode(text: str) -> bytes:
    n = 0
    for c in text:
        if c not in _B58_INDEX:
            raise ValueError(f"invalid Base58 character {c!r}")
        n = n * 58 + _B58_INDEX[c]
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    leading_ones = len(text) - len(text.lstrip("1"))
    return b"\x00" * leading_ones + body


def b58check_encode(payload: bytes) -> str:
    return b58encode(payload + double_sha256(payload)[:4])


def b58check_decode(text: str) -> bytes:
    raw = b58decode(text)
    if len(raw) < 5:
        raise ValueError("Base58Check string too short")
    payload, checksum = raw[:-4], raw[-4:]
    if double_sha256(payload)[:4] != checksum:
        raise ValueError("Base58Check checksum mismatch")
    return payload
