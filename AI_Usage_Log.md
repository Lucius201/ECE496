# AI Usage Log – ECE 496C/519C Assignment 1

**Student:** Lucius Lechner
**AI tool used:** Claude Code (Anthropic), model Claude Opus 5.5
**Date:** 2026-10-18

## 1. Prompt

> "ace the task in @task"

The only input was the assignment handout PDF (`task/ECE 496C 519C Blockchain Assignment 1.pdf`).

Follow-up prompt:

> "add a README.md explaining each py file and the whole program"

This added the architecture, flow and file-by-file sections of `README.md`.

## 2. What the AI generated

| File                                               | AI output                                                                                                                                                                                             |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/crypto_utils.py`                              | secp256k1 point add, double and scalar multiply; SHA-256, double SHA-256 and RIPEMD-160 helpers; Base58/Base58Check                                                                                   |
| `src/wallet.py`                                    | P2PKH address derivation, WIF encoding, prefix rule (accents, hyphens and apostrophes; continue into the last name), multi-process vanity search, `keypair.json` save/load with an integrity re-check |
| `src/keygen.py`                                    | one-time vanity key generation command                                                                                                                                                                |
| `src/blockchain.py`                                | Block dataclass, hardcoded genesis, hash input format, PoW miner with SHA-256 state copying, the four validation checks, First-Valid-Block-Wins append                                                |
| `src/node.py`                                      | HTTP server (`/status`, `/chain`, `/pending`, `/message`, `/mine`, `/block`), parallel broadcast with offline-peer warnings, the mining lock that makes the fork reproducible                         |
| `src/main.py`                                      | CLI (`--config`, `--vanity-prefix`, `--difficulty`), interactive console                                                                                                                              |
| `src/node1-3.json`, `src/keypair.json`             | configs; vanity keypair `1LuCB6yU1yVrkewvVh5q2bQumHpckTPHPw` (found after 8,293 tries, 0.18 s)                                                                                                        |
| `tests/test_blockchain.py`, `scripts/fork_demo.sh` | unit tests; fork-demo helper                                                                                                                                                                          |
| `README.md`, this file                             | documentation                                                                                                                                                                                         |

### Key design decisions proposed by the AI

- **Standard library only.** No Flask or ecdsa, so the curve math and HTTP routing can be explained line by line.
- **Hash input:** `index|timestamp|prev_hash|data_json|nonce|miner_address`, with `data` as compact JSON so messages containing `|` stay unambiguous.
- **Mining lock:** incoming blocks wait until a local mining cycle has finished. This makes the required Node2/Node3 fork demo reproducible instead of depending on a race of a few milliseconds.

### Bug found during testing and fixed by the AI

The first version used second-precision timestamps. Every node uses the same miner address, so Node2 and Node3 mining `[]` in the same second built the same hash input and mined the *identical* block. It was accepted as a "duplicate", so no fork appeared. Mined-block timestamps now have microsecond precision.

### Later refinements (after the student's test runs)

- Added a root `main.py` launcher so the handout command also works from the repository root.
- Clearer rejection reasons: a block whose parent is not on our chain is now reported as "different branch … -> FORK" instead of "stale" or "does not extend our tip".
- `readline` is now loaded so arrow keys and history work in the node console.

## 3. Verification performed

- Checked against known vectors: private key `1` gives address `1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH` and WIF `KwDiBf89…oWn`. The handout's example address `1JuSFZ4T…` passes Base58Check.
- 15 unit tests pass (`python3 -m unittest discover -s tests -v`).
- Ran 3 real nodes locally:
    - Node1 mined Block #1 at difficulty 4, and Node2 and Node3 each logged 4× PASS and accepted it.
    - At difficulty 6, mining on Node2 and Node3 at the same time produced a fork: each rejected the other's block with `CONFLICT at height 1 -> FORK`, and Node1 sided with the first block it received.
    - A tampered block was rejected (409) and a malformed block was rejected (400).
    - With Node3 offline, Node1 logged a warning and kept running.

## 4. Student modifications and review

_(To be completed by the student. List any changes you made to the generated code, and confirm you have reviewed and understand every file before the viva.)_

-
