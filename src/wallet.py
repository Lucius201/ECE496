"""
Part 1 - Legacy Bitcoin (P2PKH) vanity address generator.

Address derivation (standard Bitcoin Legacy / P2PKH):
  1. private key k (random 256-bit integer in [1, N-1]); public key Q = k * G
  2. compressed public key (33 bytes) = 0x02|0x03 || X(Q)
  3. pubkey_hash = RIPEMD160(SHA256(compressed_pubkey))            (20 bytes)
  4. versioned   = 0x00 || pubkey_hash                             (21 bytes)
  5. checksum    = SHA256(SHA256(versioned))[:4]                   (4 bytes)
  6. address     = Base58(versioned || checksum)                   (25 bytes -> '1...')

Vanity rule: characters 2-4 of the address (address[1:4]) must equal the
3-letter prefix, compared case-insensitively.
"""

import json
import multiprocessing as mp
import os
import queue
import secrets
import time
import unicodedata
from datetime import datetime, timezone

from crypto_utils import (
    G,
    N,
    b58check_decode,
    b58check_encode,
    b58encode,
    compress_pubkey,
    double_sha256,
    hash160,
    is_on_curve,
    point_add,
    scalar_mult,
)

MAINNET_P2PKH_VERSION = b"\x00"
MAINNET_WIF_VERSION = b"\x80"


# --------------------------------------------------------------------------- #
# Address derivation
# --------------------------------------------------------------------------- #
def generate_private_key() -> int:
    """Cryptographically secure random scalar in [1, N-1]."""
    return secrets.randbelow(N - 1) + 1


def pubkey_to_address(compressed_pubkey: bytes) -> str:
    versioned = MAINNET_P2PKH_VERSION + hash160(compressed_pubkey)
    checksum = double_sha256(versioned)[:4]
    return b58encode(versioned + checksum)


def private_key_to_wif(private_key: int) -> str:
    # Trailing 0x01 marks "use the compressed public key"
    return b58check_encode(MAINNET_WIF_VERSION + private_key.to_bytes(32, "big") + b"\x01")


def derive_identity(private_key: int) -> dict:
    """Derive every public value from a private key."""
    point = scalar_mult(private_key, G)
    pub = compress_pubkey(point)
    return {
        "private_key_hex": private_key.to_bytes(32, "big").hex(),
        "private_key_wif": private_key_to_wif(private_key),
        "public_key_compressed_hex": pub.hex(),
        "public_key_hash160_hex": hash160(pub).hex(),
        "address": pubkey_to_address(pub),
    }


def is_valid_address(address: str) -> bool:
    """Base58Check-decode and check version byte + payload length."""
    try:
        payload = b58check_decode(address)
    except ValueError:
        return False
    return len(payload) == 21 and payload[:1] == MAINNET_P2PKH_VERSION


# --------------------------------------------------------------------------- #
# Vanity prefix rules
# --------------------------------------------------------------------------- #
def _ascii_letters(text: str) -> str:
    """Strip accents (e.g. 'É' -> 'E'), drop hyphens/apostrophes/anything non A-Z."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if "A" <= c.upper() <= "Z" and c.isascii()).upper()


def prefix_from_name(first_name: str, last_name: str = "") -> str:
    """First three letters of the first name, continuing into the last name if needed."""
    letters = _ascii_letters(first_name) + _ascii_letters(last_name)
    if len(letters) < 3:
        raise ValueError("name must contain at least 3 letters (A-Z)")
    return letters[:3]


def normalize_prefix(prefix: str) -> str:
    letters = _ascii_letters(prefix)
    if len(letters) < 3:
        raise ValueError(f"vanity prefix {prefix!r} must contain 3 letters (A-Z)")
    return letters[:3]


def matches_prefix(address: str, prefix: str) -> bool:
    return address.startswith("1") and address[1:4].upper() == prefix.upper()


# --------------------------------------------------------------------------- #
# Vanity search (multi-process)
#
# Each worker picks a random starting key k and then walks k, k+1, k+2, ...
# The matching public keys are Q, Q+G, Q+2G, ... so each candidate costs one
# point addition instead of a full 256-bit scalar multiplication. This is the
# standard trick used by real vanity generators.
# --------------------------------------------------------------------------- #
_REPORT_EVERY = 2000


def _search_worker(prefix, found_event, result_queue, counter):
    k = generate_private_key()
    point = scalar_mult(k, G)
    local = 0
    while not found_event.is_set():
        pub = compress_pubkey(point)
        address = pubkey_to_address(pub)
        local += 1
        if matches_prefix(address, prefix):
            result_queue.put((k, address))
            found_event.set()
            break
        k += 1
        if k >= N:  # astronomically unlikely, but stay inside the group
            k = generate_private_key()
            point = scalar_mult(k, G)
        else:
            point = point_add(point, G)
        if local % _REPORT_EVERY == 0:
            with counter.get_lock():
                counter.value += _REPORT_EVERY
    with counter.get_lock():
        counter.value += local % _REPORT_EVERY


def search_vanity(prefix: str, workers: int = None, progress=print) -> dict:
    """Search for a key whose address matches the prefix. Returns a keypair dict."""
    prefix = normalize_prefix(prefix)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    ctx = mp.get_context("spawn")
    found_event = ctx.Event()
    result_queue = ctx.Queue()
    counter = ctx.Value("Q", 0)

    procs = [
        ctx.Process(target=_search_worker, args=(prefix, found_event, result_queue, counter), daemon=True)
        for _ in range(workers)
    ]
    start = time.time()
    progress(f"[+] Searching for vanity prefix '1{prefix}...' (case-insensitive) using {workers} worker(s)")
    for p in procs:
        p.start()

    last_report = start
    while True:
        try:
            k, address = result_queue.get(timeout=0.5)
            break
        except queue.Empty:
            now = time.time()
            if now - last_report >= 5:
                rate = counter.value / max(now - start, 1e-9)
                progress(f"    ... {counter.value:,} addresses tried ({rate:,.0f}/s)")
                last_report = now

    for p in procs:
        p.join(timeout=2)
        if p.is_alive():
            p.terminate()
    elapsed = time.time() - start

    identity = derive_identity(k)
    assert identity["address"] == address
    return {
        "warning": "FOR ECE 496C/519C ASSIGNMENT USE ONLY - NEVER SEND REAL FUNDS TO THIS ADDRESS",
        "vanity_prefix": prefix,
        **identity,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "search_stats": {"addresses_tried": counter.value, "seconds": round(elapsed, 2), "workers": workers},
    }


# --------------------------------------------------------------------------- #
# keypair.json persistence
# --------------------------------------------------------------------------- #
def save_keypair(keypair: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(keypair, fh, indent=2)
        fh.write("\n")


def load_keypair(path: str) -> dict:
    """Load keypair.json and re-derive everything from the private key to verify it."""
    with open(path, "r", encoding="utf-8") as fh:
        stored = json.load(fh)
    private_key = int(stored["private_key_hex"], 16)
    if not 0 < private_key < N:
        raise ValueError("private key out of range")
    derived = derive_identity(private_key)
    if not is_on_curve(scalar_mult(private_key, G)):
        raise ValueError("derived public key is not on secp256k1")
    for field in ("public_key_compressed_hex", "address"):
        if stored.get(field) != derived[field]:
            raise ValueError(f"keypair.json is inconsistent: stored {field} does not match private key")
    return {**stored, **derived}
