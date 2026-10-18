"""
Part 2 - Block data structure, hashing, Proof-of-Work mining and validation.

Block hash pre-image (the `hash` field is NOT part of it):

    "{index}|{timestamp}|{prev_hash}|{data_json}|{nonce}|{miner_address}"

  * index          decimal integer, no padding           e.g. 1
  * timestamp      ISO-8601 UTC with microseconds         e.g. 2026-10-18T14:03:07.482913Z
                   (genesis keeps its hardcoded "2026-01-01T00:00:00Z")
  * prev_hash      64 lowercase hex chars
  * data_json      json.dumps(data, separators=(",", ":"), ensure_ascii=False)
                   e.g. ["hello","world"]   or   []  for an empty block
  * nonce          decimal integer, no padding
  * miner_address  Base58 P2PKH address (or "GENESIS")

The pre-image is UTF-8 encoded and hashed once with SHA-256; the hex digest
(lowercase) is the block hash. Encoding `data` as compact JSON keeps the
pre-image unambiguous even if a message contains the "|" separator.
"""

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

DEFAULT_DIFFICULTY = 4
ZERO_HASH = "0" * 64


def utc_timestamp() -> str:
    # Microsecond precision: every node stamps blocks with the same vanity address,
    # so two nodes mining the same data in the same second would otherwise build an
    # identical pre-image, find the identical nonce and produce the *same* block.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def serialize_data(data) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def hash_preimage(index, timestamp, prev_hash, data, nonce, miner_address) -> str:
    return f"{index}|{timestamp}|{prev_hash}|{serialize_data(data)}|{nonce}|{miner_address}"


def compute_hash(index, timestamp, prev_hash, data, nonce, miner_address) -> str:
    preimage = hash_preimage(index, timestamp, prev_hash, data, nonce, miner_address)
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


@dataclass
class Block:
    index: int
    prev_hash: str
    timestamp: str
    data: list
    nonce: int
    miner_address: str
    hash: str = field(default="")

    def calculate_hash(self) -> str:
        return compute_hash(self.index, self.timestamp, self.prev_hash, self.data, self.nonce, self.miner_address)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        """Strictly parse a block received from the network (rejects malformed input)."""
        if not isinstance(d, dict):
            raise ValueError("block must be a JSON object")
        expected = {"index", "prev_hash", "timestamp", "data", "nonce", "miner_address", "hash"}
        missing = expected - d.keys()
        if missing:
            raise ValueError(f"missing field(s): {', '.join(sorted(missing))}")
        for name in ("index", "nonce"):
            if not isinstance(d[name], int) or isinstance(d[name], bool) or d[name] < 0:
                raise ValueError(f"'{name}' must be a non-negative integer")
        for name in ("prev_hash", "timestamp", "miner_address", "hash"):
            if not isinstance(d[name], str):
                raise ValueError(f"'{name}' must be a string")
        if not isinstance(d["data"], list) or not all(isinstance(m, str) for m in d["data"]):
            raise ValueError("'data' must be an array of strings")
        return cls(**{k: d[k] for k in expected})

    def short(self) -> str:
        return f"#{self.index} {self.hash[:16]}... miner={self.miner_address}"


# --------------------------------------------------------------------------- #
# Hardcoded genesis block - identical on every node, trusted, no PoW check.
# --------------------------------------------------------------------------- #
def make_genesis() -> Block:
    genesis = Block(
        index=0,
        prev_hash=ZERO_HASH,
        timestamp="2026-01-01T00:00:00Z",
        data=["Genesis Block"],
        nonce=0,
        miner_address="GENESIS",
    )
    genesis.hash = genesis.calculate_hash()
    return genesis


GENESIS_BLOCK = make_genesis()


# --------------------------------------------------------------------------- #
# Proof-of-Work
# --------------------------------------------------------------------------- #
def mine_block(index, prev_hash, data, miner_address, difficulty, on_progress=None, progress_every=500_000):
    """
    Brute-force a nonce so that SHA-256(pre-image) starts with `difficulty` hex zeros.

    Optimisation: the pre-image is "<prefix><nonce><suffix>" where prefix and
    suffix never change, so the SHA-256 state of the prefix is computed once and
    copied for each attempt. The resulting hash is identical to compute_hash().

    on_progress(nonce, hash_hex, elapsed) is called for nonce 0, every
    `progress_every` attempts, and for the winning nonce.
    """
    timestamp = utc_timestamp()
    target = "0" * difficulty
    prefix = f"{index}|{timestamp}|{prev_hash}|{serialize_data(data)}|".encode("utf-8")
    suffix = f"|{miner_address}".encode("utf-8")
    base = hashlib.sha256(prefix)

    start = time.time()
    nonce = 0
    while True:
        h = base.copy()
        h.update(str(nonce).encode() + suffix)
        digest = h.hexdigest()
        if digest.startswith(target):
            break
        if on_progress and (nonce == 0 or nonce % progress_every == 0):
            on_progress(nonce, digest, time.time() - start)
        nonce += 1
    elapsed = time.time() - start

    block = Block(index, prev_hash, timestamp, list(data), nonce, miner_address, digest)
    if on_progress:
        on_progress(nonce, digest, elapsed)
    return block, elapsed


# --------------------------------------------------------------------------- #
# Validation (Part 3 checklist)
# --------------------------------------------------------------------------- #
def validate_block(block: Block, tip: Block, difficulty: int):
    """
    Run the four required checks against our current tip.
    Returns (ok, checks) where checks is a list of (name, passed, detail).
    All four checks are always evaluated so the log shows exactly what failed.
    """
    recomputed = block.calculate_hash()
    target = "0" * difficulty
    checks = [
        ("Hash Verification", recomputed == block.hash,
         f"recomputed {recomputed[:16]}... {'==' if recomputed == block.hash else '!='} claimed {block.hash[:16]}..."),
        ("Difficulty Verification", recomputed.startswith(target),
         f"hash {'starts' if recomputed.startswith(target) else 'does NOT start'} with \"{target}\""),
        ("Chain Continuity", block.prev_hash == tip.hash,
         f"prev_hash {block.prev_hash[:16]}... {'==' if block.prev_hash == tip.hash else '!='} our tip {tip.hash[:16]}..."),
        ("Index Sequence", block.index == tip.index + 1,
         f"index {block.index} {'==' if block.index == tip.index + 1 else '!='} tip index + 1 ({tip.index + 1})"),
    ]
    return all(passed for _, passed, _ in checks), checks


def classify_rejection(block: Block, chain: list) -> str:
    """Human-readable explanation of *why* a structurally valid block does not fit."""
    tip = chain[-1]
    if block.index == 0:
        return "genesis is hardcoded and cannot be replaced"
    if block.index > tip.index + 1:
        return f"block is ahead of our chain (we are at height {tip.index}; no sync in A1)"
    if block.index <= tip.index and chain[block.index].hash == block.hash:
        return "duplicate - we already have this block"
    parent = chain[block.index - 1]  # the block that *should* be its parent on our chain
    if block.prev_hash != parent.hash:
        return (f"different branch: its parent {block.prev_hash[:16]}... is not our block "
                f"#{parent.index} {parent.hash[:16]}... -> FORK")
    if block.index <= tip.index:
        return (f"CONFLICT at height {block.index}: we already accepted {chain[block.index].hash[:16]}... "
                f"(First-Valid-Block-Wins) -> FORK")
    return "does not extend our current tip"


class Blockchain:
    """In-memory chain protected by a lock (HTTP handlers run on multiple threads)."""

    def __init__(self):
        self._blocks = [make_genesis()]
        self.lock = threading.RLock()

    @property
    def tip(self) -> Block:
        with self.lock:
            return self._blocks[-1]

    @property
    def height(self) -> int:
        with self.lock:
            return self._blocks[-1].index

    def snapshot(self) -> list:
        with self.lock:
            return list(self._blocks)

    def try_append(self, block: Block, difficulty: int):
        """Validate against the current tip and append atomically. Returns (ok, checks, reason)."""
        with self.lock:
            ok, checks = validate_block(block, self._blocks[-1], difficulty)
            if ok:
                self._blocks.append(block)
                return True, checks, "accepted"
            hash_ok = checks[0][1] and checks[1][1]
            reason = classify_rejection(block, self._blocks) if hash_ok else "invalid hash / proof-of-work"
            return False, checks, reason
