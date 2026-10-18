"""Run from the repository root:  python3 -m unittest discover -s tests -v"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from blockchain import GENESIS_BLOCK, Block, Blockchain, compute_hash, hash_preimage, mine_block, validate_block  # noqa: E402
from crypto_utils import G, N, b58check_decode, b58decode, b58encode, is_on_curve, scalar_mult  # noqa: E402
from wallet import (  # noqa: E402
    derive_identity, is_valid_address, load_keypair, matches_prefix, normalize_prefix, prefix_from_name,
)

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
ADDR = "1LuCB6yU1yVrkewvVh5q2bQumHpckTPHPw"


class TestPart1Wallet(unittest.TestCase):
    def test_known_vector_private_key_1(self):
        ident = derive_identity(1)
        self.assertEqual(ident["public_key_compressed_hex"],
                         "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")
        self.assertEqual(ident["address"], "1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH")
        self.assertEqual(ident["private_key_wif"], "KwDiBf89QgGbjEhKnhXJuH7LrciVrZi3qYjgd9M7rFU73sVHnoWn")

    def test_curve_math(self):
        self.assertTrue(is_on_curve(G))
        self.assertEqual(scalar_mult(N - 1, G)[0], G[0])  # (N-1)G = -G

    def test_base58_roundtrip(self):
        for raw in (b"", b"\x00", b"\x00\x00\x01", os.urandom(25)):
            self.assertEqual(b58decode(b58encode(raw)), raw)

    def test_handout_example_address_is_valid(self):
        self.assertTrue(is_valid_address("1JuSFZ4T582XUQUKsP47M5fEPeYTQ8mP1z"))
        self.assertTrue(matches_prefix("1JuSFZ4T582XUQUKsP47M5fEPeYTQ8mP1z", "JUS"))
        self.assertFalse(is_valid_address("1JuSFZ4T582XUQUKsP47M5fEPeYTQ8mP1y"))  # bad checksum

    def test_prefix_rule(self):
        self.assertEqual(prefix_from_name("Lucius", "Lechner"), "LUC")
        self.assertEqual(prefix_from_name("Bo", "Li"), "BOL")       # short first name -> continue with last
        self.assertEqual(prefix_from_name("Él", "O'Neil"), "ELO")  # accents/apostrophes ignored
        self.assertEqual(prefix_from_name("Jean-Luc"), "JEA")
        self.assertEqual(normalize_prefix("luc"), "LUC")

    def test_submitted_keypair(self):
        kp = load_keypair(os.path.join(SRC, "keypair.json"))  # re-derives and cross-checks everything
        self.assertEqual(kp["address"], ADDR)
        self.assertTrue(matches_prefix(kp["address"], "LUC"))
        self.assertEqual(len(bytes.fromhex(kp["public_key_compressed_hex"])), 33)
        self.assertEqual(len(b58check_decode(kp["address"])), 21)


class TestPart2Blocks(unittest.TestCase):
    def test_genesis_fields(self):
        g = GENESIS_BLOCK
        self.assertEqual((g.index, g.prev_hash, g.timestamp, g.nonce, g.miner_address, g.data),
                         (0, "0" * 64, "2026-01-01T00:00:00Z", 0, "GENESIS", ["Genesis Block"]))
        self.assertEqual(g.hash, hashlib.sha256(
            b'0|2026-01-01T00:00:00Z|' + b"0" * 64 + b'|["Genesis Block"]|0|GENESIS').hexdigest())

    def test_preimage_format(self):
        self.assertEqual(hash_preimage(1, "T", "P", ["a", "b|c"], 7, "M"), '1|T|P|["a","b|c"]|7|M')
        self.assertEqual(hash_preimage(1, "T", "P", [], 7, "M"), "1|T|P|[]|7|M")

    def test_mined_block_hash_matches_reference(self):
        block, _ = mine_block(1, GENESIS_BLOCK.hash, ["hello"], ADDR, 3)
        self.assertTrue(block.hash.startswith("000"))
        self.assertEqual(block.hash, compute_hash(block.index, block.timestamp, block.prev_hash,
                                                  block.data, block.nonce, block.miner_address))


class TestPart3Validation(unittest.TestCase):
    def setUp(self):
        self.chain = Blockchain()
        self.b1, _ = mine_block(1, GENESIS_BLOCK.hash, ["x"], ADDR, 3)

    def test_valid_block_accepted(self):
        ok, checks, _ = self.chain.try_append(self.b1, 3)
        self.assertTrue(ok)
        self.assertTrue(all(p for _, p, _ in checks))
        self.assertEqual(self.chain.height, 1)

    def test_tampered_data_fails_hash_check(self):
        bad = Block(**{**self.b1.to_dict(), "data": ["evil"]})
        ok, checks = validate_block(bad, GENESIS_BLOCK, 3)
        self.assertFalse(ok)
        self.assertFalse(checks[0][1])

    def test_insufficient_difficulty(self):
        ok, checks = validate_block(self.b1, GENESIS_BLOCK, 12)
        self.assertFalse(ok)
        self.assertTrue(checks[0][1])
        self.assertFalse(checks[1][1])

    def test_wrong_parent_and_index(self):
        orphan, _ = mine_block(5, "ab" * 32, [], ADDR, 2)
        ok, checks = validate_block(orphan, GENESIS_BLOCK, 2)
        self.assertFalse(checks[2][1])
        self.assertFalse(checks[3][1])

    def test_first_valid_block_wins_rejects_same_height(self):
        competitor, _ = mine_block(1, GENESIS_BLOCK.hash, ["y"], ADDR, 3)
        self.assertTrue(self.chain.try_append(self.b1, 3)[0])
        ok, _, reason = self.chain.try_append(competitor, 3)
        self.assertFalse(ok)
        self.assertIn("FORK", reason)
        self.assertEqual(self.chain.tip.hash, self.b1.hash)

    def test_block_from_other_branch_reported_as_fork(self):
        # Our chain: genesis <- b1.  Other branch: genesis <- c1 <- c2.
        c1, _ = mine_block(1, GENESIS_BLOCK.hash, ["other"], ADDR, 3)
        c2, _ = mine_block(2, c1.hash, [], ADDR, 3)
        self.assertTrue(self.chain.try_append(self.b1, 3)[0])
        ok, _, reason = self.chain.try_append(c2, 3)          # height 2 = tip+1, wrong parent
        self.assertFalse(ok)
        self.assertIn("different branch", reason)
        self.assertIn("FORK", reason)
        b2, _ = mine_block(2, self.b1.hash, [], ADDR, 3)
        self.assertTrue(self.chain.try_append(b2, 3)[0])
        ok, _, reason = self.chain.try_append(c2, 3)          # now same height as our tip
        self.assertIn("different branch", reason)

    def test_from_dict_rejects_malformed(self):
        for bad in ({}, {**self.b1.to_dict(), "index": "1"}, {**self.b1.to_dict(), "data": "x"},
                    {**self.b1.to_dict(), "nonce": True}):
            with self.assertRaises(ValueError):
                Block.from_dict(bad)


if __name__ == "__main__":
    unittest.main()
