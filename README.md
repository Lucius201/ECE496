# ECE 496C / 519C – Assignment 1: Lightweight Layer-1 Blockchain

**Student:** Lucius Lechner &nbsp;·&nbsp; **Vanity prefix:** `LUC` &nbsp;·&nbsp; **Address:** `1LuCB6yU1yVrkewvVh5q2bQumHpckTPHPw`

This project is a 3-node Proof-of-Work blockchain written in **Python 3 using only the standard library**. You don't need to `pip install` anything. It has three parts:

- **Part 1:** A Legacy Bitcoin (P2PKH) vanity address generator. It uses hand-written secp256k1 curve math, SHA-256, RIPEMD-160 and Base58Check.
- **Part 2:** A hardcoded genesis block, a deterministic block hash, and mining that runs only on command (`mine`, or `POST /mine`). Mining picks up pending messages added with `msg <text>` or `POST /message`.
- **Part 3:** HTTP peer-to-peer networking. Every incoming block goes through the four validation checks, and the network follows the First-Valid-Block-Wins rule, so you can show the fork limitation.

> ⚠️ `keypair.json` is for this assignment only. **Never send real funds to this address.**

**Contents:**

1. [Quick start](#1-quick-start)
2. [Project layout](#2-project-layout)
3. [How the whole program works](#3-how-the-whole-program-works)
4. [File-by-file guide](#4-file-by-file-guide)
5. [Running the nodes](#5-running-the-nodes)
6. [Block hashing: exact field order and format](#6-block-hashing-exact-field-order-and-format)
7. [Validation & consensus](#7-validation--consensus)
8. [Demo script](#8-demo-script-15-minute-slot)
9. [Tests](#9-tests)

---

## 1. Quick start

Run the commands from the repository root **or** from `src/`; both work. The root `main.py` is a small launcher for `src/main.py`, and `node1.json` / `keypair.json` are found in `src/` automatically.

```bash
# three terminals:
python3 main.py --config node1.json --vanity-prefix LUC --difficulty 4
python3 main.py --config node2.json --vanity-prefix LUC --difficulty 4
python3 main.py --config node3.json --vanity-prefix LUC --difficulty 4
# then in Node1's terminal:
Node1> msg Hello
Node1> mine
```

Requirements: Python **3.8+** (developed and tested on 3.13). Run `python3 -c "import hashlib; hashlib.new('ripemd160')"`. If it raises an error, your OpenSSL build has RIPEMD-160 disabled: run `pip install pycryptodome`, and the code switches to `Crypto.Hash.RIPEMD160` on its own.

## 2. Project layout

```
README.md              this file
main.py                launcher: runs src/main.py, so the handout command works from the root
AI_Usage_Log.md        generative-AI usage log
requirements.txt       (no third-party dependencies)
src/
  crypto_utils.py      secp256k1 point math, SHA-256 / RIPEMD-160, Base58(Check)
  wallet.py            Part 1: P2PKH address, prefix rule, vanity search, keypair.json I/O
  keygen.py            one-time command: search vanity key -> keypair.json
  blockchain.py        Part 2: Block, genesis, hash pre-image, PoW miner, validation, chain
  node.py              Part 3: HTTP server, broadcast to peers, receive + validate
  main.py              entry point: CLI flags, identity loading, interactive console
  node1.json node2.json node3.json    per-node id / port / peers
  keypair.json         pre-computed vanity keypair (prefix LUC)
scripts/fork_demo.sh   fire /mine on Node2 and Node3 at the same instant
tests/test_blockchain.py   unit tests for all three parts
```

---

## 3. How the whole program works

### 3.1 Architecture

The modules are layered, and each one imports only from the layers below it. `main.py` wires everything together: it loads the identity with `wallet.py` and hands the address to a `Node`. `node.py` itself never touches keys.

```
                       ┌──────────────────────────────────────────┐
        user ────────► │ main.py   CLI flags · identity · console │
                       └────┬────────────────┬───────────────┬────┘
               creates Node │       GENESIS, │               │ loads keypair
                            ▼       defaults │               ▼
 other   HTTP/JSON  ┌────────────────────┐   │   ┌─────────────────────────┐
 nodes ◄──────────► │ node.py            │   │   │ wallet.py               │ ◄── keygen.py
                    │ HTTP server ·      │   │   │ address · prefix ·      │
                    │ broadcast ·        │   │   │ vanity · keypair.json   │
                    │ receive · locks    │   │   └────────────┬────────────┘
                    └─────────┬──────────┘   │                │ uses
                              │ uses         │                ▼
                              ▼              │   ┌─────────────────────────┐
                    ┌────────────────────┐   │   │ crypto_utils.py         │
                    │ blockchain.py      │ ◄─┘   │ secp256k1 · hash160 ·   │
                    │ Block · genesis ·  │       │ Base58(Check)           │
                    │ hashing · mining · │       └─────────────────────────┘
                    │ validation · chain │
                    └────────────────────┘
```

Each node is one Python process. Running the assignment means starting **three processes** from the same code. Each gets a different config file (`node1.json` …). They all load the same `keypair.json` and talk to each other over HTTP on `127.0.0.1:8001-8003`.

Inside one process there are three kinds of thread:

| Thread              | What it does                                                                                                                                    |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| main thread         | the interactive console (`repl()` in `main.py`); `mine` typed here runs the PoW on this thread, so the console is busy until the block is found |
| HTTP server threads | `ThreadingHTTPServer` starts one thread per incoming request (`/block`, `/mine`, `/status`, …)                                                  |
| broadcast threads   | one short-lived thread per peer, so that a slow or offline peer never blocks the others                                                         |

Two locks keep this safe:

- **`Blockchain.lock`** (an `RLock`) makes "validate against the tip, then append" atomic.
- **`Node.mining_lock`** is held for a whole mining cycle. A block arriving from a peer waits on this lock, so it is processed only **after** the local mining cycle finishes. §3.5 explains why.

### 3.2 Startup: `python3 main.py --config node1.json --vanity-prefix LUC --difficulty 4`

1. `main()` parses the flags and checks that the difficulty is between 1 and 64. It then normalises the prefix (`"luc"` → `"LUC"`) and loads `node1.json`.
2. `init_identity()` runs `wallet.load_keypair()`. That function does not trust the file: it recomputes the public key and address from the private key and compares them with the stored values. It then checks `matches_prefix(address, "LUC")` and prints `MATCH FOUND`. If the stored address does **not** match the prefix, the node exits and prints the `keygen.py ... --force` command to fix it. If `keypair.json` is missing, it runs the vanity search once and saves the result (or exits, with `--no-search`).
3. A `Node` is created. Its `Blockchain` starts with the **hardcoded genesis block** (`make_genesis()`), which is identical on every node.
4. `node.start_server()` starts the HTTP server on a background thread.
5. `repl()` reads commands until `quit` (or Ctrl-C). If stdin reaches end-of-file (for example, the node was started with `< /dev/null` or in the background), the node keeps running headless and serves HTTP only.

### 3.3 Mining a block: `mine` or `POST /mine` → `Node.mine()`

```
acquire mining_lock ─► read tip ─► take pending messages ─► mine_block() PoW loop
     ─► chain.try_append(own block) ─► drop mined messages from pending ─► release lock
     ─► broadcast(block) to every peer in parallel ─► log ACCEPTED / REJECTED / WARN per peer
```

- `mine_block()` (in `blockchain.py`) builds the hash input `index|timestamp|prev_hash|data|nonce|miner_address`. It then tries nonce = 0, 1, 2, … until the SHA-256 hex digest starts with `difficulty` zeros.
- The node adds the block to **its own chain first**, then broadcasts it. That order is required by the handout.
- If there are no pending messages, the block is mined with `data = []`.
- Messages added _while_ mining stay pending for the next block.

### 3.4 Receiving a block: `POST /block` → `Node.receive_block()`

```
parse JSON strictly (Block.from_dict) ──bad──► 400 malformed
        │
wait for mining_lock (logs "queued" if we are mining right now)
        │
chain.try_append(): validate_block() runs the 4 checks against our tip
        ├── all pass  ──► append ─► 200 {"accepted": true}
        └── any fails ──► classify_rejection() ─► 409 {"reason": "...FORK" | "invalid hash" | ...}
```

The 4 checks are hash verification, difficulty, chain continuity and index sequence. Every check is logged as `PASS` or `FAIL`. Received blocks are **not** forwarded again, because every node already connects directly to every other node.

### 3.5 Why the fork happens (First-Valid-Block-Wins)

Suppose Node2 and Node3 both start mining height 1 on top of genesis:

```
t0  Node2: mine (holds its mining_lock)       Node3: mine (holds its mining_lock)
t1  Node2 finds block A, appends A, broadcasts
      → Node1 accepts A  (first valid block for height 1)
      → Node3 is still mining: A is queued
t2  Node3 finds block B, appends B, broadcasts
      → Node1 rejects B: prev_hash ≠ tip(A), index ≠ tip+1  ⇒ CONFLICT → FORK
      → Node2 rejects B for the same reason
t3  Node3 processes the queued block A ⇒ rejects it (its tip is B) ⇒ FORK

Result:  Node1 & Node2 on A   |   Node3 on B   — neither side gives way
```

The local miner is never interrupted, so whenever two mining cycles overlap, each miner keeps its own block. Raising the difficulty to 6 makes each cycle last a few seconds, so the overlap is easy to trigger. The most-work chain rule in Assignment 2 is what will resolve such splits.

---

## 4. File-by-file guide

### `src/crypto_utils.py`: cryptographic primitives (no project logic)

| Function                              | Purpose                                                                                                                                                      |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `P, N, G`                             | secp256k1 constants: field prime, group order, generator point. The curve is `y² = x³ + 7 (mod P)`                                                           |
| `point_add(p1, p2)`                   | elliptic-curve point addition and doubling (affine coordinates). The point at infinity is `None`. Uses `pow(x, -1, P)` for the modular inverse               |
| `scalar_mult(k, point)`               | computes `k·point` by **double-and-add**: one doubling per bit of k plus one addition per 1-bit. With `point = G` this turns a private key into a public key |
| `is_on_curve(point)`                  | sanity check `y² − x³ − 7 ≡ 0 (mod P)`                                                                                                                       |
| `compress_pubkey(point)`              | 33-byte SEC1 encoding: `0x02` (y even) or `0x03` (y odd), followed by the 32-byte `x`                                                                        |
| `sha256`, `double_sha256`             | thin `hashlib` wrappers                                                                                                                                      |
| `ripemd160`, `hash160`                | `hash160(x) = RIPEMD160(SHA256(x))`. `_make_ripemd160()` uses `hashlib` if it supports RIPEMD-160, otherwise pycryptodome                                    |
| `b58encode` / `b58decode`             | Base58 with the Bitcoin alphabet (no `0 O I l`). Each leading `0x00` byte becomes a `'1'`, which is why every address starts with `1`                        |
| `b58check_encode` / `b58check_decode` | Base58 plus a 4-byte double-SHA-256 checksum, which is verified on decode                                                                                    |

### `src/wallet.py`: Part 1, address generation and vanity search

| Function                                          | Purpose                                                                                                                                                                                                                     |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `generate_private_key()`                          | random `k ∈ [1, N-1]` from the `secrets` module (a CSPRNG)                                                                                                                                                                  |
| `pubkey_to_address(pub)`                          | the P2PKH steps: `0x00 + hash160(pub)` → append `double_sha256(...)[:4]` → Base58                                                                                                                                           |
| `private_key_to_wif(k)`                           | Wallet Import Format: `0x80 + k + 0x01` (the 0x01 flag means "compressed"), Base58Check                                                                                                                                     |
| `derive_identity(k)`                              | computes every public value from a private key: hex and WIF private key, compressed public key, hash160, address                                                                                                            |
| `is_valid_address(addr)`                          | Base58Check decode, then check the version byte `0x00` and the 21-byte payload length                                                                                                                                       |
| `prefix_from_name(first, last)`                   | the handout's rule: first 3 letters A–Z of the first name, continuing into the last name. Accents are removed via Unicode NFKD, and hyphens and apostrophes are dropped                                                     |
| `normalize_prefix(p)` / `matches_prefix(addr, p)` | the vanity test is `addr[1:4].upper() == p.upper()`                                                                                                                                                                         |
| `_search_worker(...)`                             | one search process. It starts at a random `k` and then steps `k+1`, `Q ← Q + G`, so each candidate costs one point addition instead of a full scalar multiplication. It stops when any worker sets the shared `found_event` |
| `search_vanity(prefix)`                           | starts one worker per CPU core minus one (`multiprocessing`, `spawn`), prints progress, collects the first match, and returns the keypair dict with search statistics                                                       |
| `save_keypair` / `load_keypair`                   | JSON persistence. `load_keypair` re-derives everything from the private key and raises an error if the stored public key or address does not match                                                                          |

### `src/keygen.py`: one-time key generation command

```bash
python3 keygen.py --name "Lucius Lechner"        # derive prefix with the name rule
python3 keygen.py --vanity-prefix LUC --force    # overwrite with a brand-new key
```

If `keypair.json` already matches the prefix, keygen just prints it and exits. It refuses to overwrite a different key unless you pass `--force`. Run it **before** the demo. The nodes themselves never search when the file exists.

### `src/blockchain.py`: Part 2, blocks, hashing, PoW, validation

| Item                                       | Purpose                                                                                                                                                                                                                                                          |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hash_preimage(...)` / `compute_hash(...)` | **the single definition of the block hash**: `index\|timestamp\|prev_hash\|data_json\|nonce\|miner_address` → SHA-256 hex (see §6)                                                                                                                               |
| `serialize_data(data)`                     | compact, deterministic JSON for the message list                                                                                                                                                                                                                 |
| `utc_timestamp()`                          | ISO-8601 UTC with microseconds. Every node uses the same miner address, so two nodes mining `[]` in the same second would otherwise produce the _same_ block, and the fork demo would fail                                                                       |
| `class Block`                              | a dataclass with the 7 fields. `calculate_hash()` hashes the 6 payload fields. `from_dict()` **strictly** parses network input: every field must be present with the right type, and `bool` is rejected where an int is expected                                 |
| `make_genesis()` / `GENESIS_BLOCK`         | the hardcoded genesis block. It is not checked for PoW                                                                                                                                                                                                           |
| `mine_block(...)`                          | the PoW loop. It hashes the constant part of the input once and calls `hashlib`'s `.copy()` for each nonce (~2.5 MH/s). It reports progress at nonce 0, every 500k nonces, and on success. The result is identical to `compute_hash()`, which a unit test checks |
| `validate_block(block, tip, difficulty)`   | runs the **4 required checks** and returns `(ok, [(name, passed, detail)…])`. All four are always evaluated, so the log shows exactly which ones failed                                                                                                          |
| `classify_rejection(block, chain)`         | explains a rejection in plain words: duplicate, **same-height conflict** or **block from a different branch** (both reported as FORK), or ahead of us (no sync in A1)                                                                                                                                                           |
| `class Blockchain`                         | the in-memory block list with an `RLock`. `try_append()` validates against the tip and appends in one locked step. `tip`, `height` and `snapshot()` are thread-safe reads                                                                                        |

### `src/node.py`: Part 3, networking and the node's behaviour

| Item                                        | Purpose                                                                                                                                                                                                                                        |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `class Console`                             | thread-safe logging. When a background thread prints (for example, "Received Block #1"), it clears and redraws the `Node1> ` prompt so the console stays readable                                                                              |
| `Node.__init__`                             | stores the id, host, port, peers (from the config), address (from the keypair), difficulty, `Blockchain`, pending messages and locks                                                                                                           |
| `add_message` / `pending_snapshot`          | local pending-message pool under `pending_lock`. Messages never leave the node except inside a mined block                                                                                                                                     |
| `mine()`                                    | the full mining cycle from §3.3. It refuses to start a second cycle while one is running                                                                                                                                                       |
| `broadcast(block)` / `_send_block(peer, …)` | sends `POST <peer>/block` to every peer on its own thread. Status 200 is logged as ACCEPTED and 409 as REJECTED with the peer's reason. A connection refused or timeout produces `[WARN] … Continuing without it.`, and the node never crashes |
| `receive_block(dict, sender)`               | the flow in §3.4. It returns `(HTTP status, JSON body)` to the handler                                                                                                                                                                         |
| `status()` / `fetch_peer_status(peer)`      | node summary (height, tip, mining flag…) and a fetch of the same summary from a peer, used by the `peers` command                                                                                                                              |
| `start_server()`                            | defines the `Handler` (a `BaseHTTPRequestHandler`) whose `do_GET`/`do_POST` route `/status`, `/chain`, `/pending`, `/message`, `/mine` and `/block`, then starts a `ThreadingHTTPServer` in a daemon thread                                    |
| `PEER_TIMEOUT_SECONDS`                      | 600 s. A peer that is busy mining at high difficulty only answers once its cycle ends, so the timeout has to be generous                                                                                                                       |

### `src/main.py`: entry point and interactive console

| Function                                    | Purpose                                                                                                                                                                          |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `main()`                                    | parses `--config`, `--vanity-prefix` and `--difficulty` (plus the optional `--keypair` and `--no-search`), loads the config and identity, starts the `Node` and runs the console |
| `init_identity(prefix, path, allow_search)` | loads and verifies `keypair.json` and prints the `Loading keypair… / Public Address / Prefix Status` lines from the handout. Searches only if the file is missing                |
| `resolve_path(p)`                           | lets you run from the repo root or from `src/`. Paths are tried relative to the current directory first, then relative to `src/`                                                 |
| `repl(node, console)`                       | the command loop: `msg`, `pending`, `mine`, `chain`, `block <n>`, `status`, `peers`, `help`, `quit`                                                                              |
| `print_chain(node)`                         | one line per block: index, hash, prev_hash, nonce, time, miner, data                                                                                                             |
| `print_peers(node)`                         | asks every peer for `/status` and prints height and tip side by side. It flags **FORK** if nodes at the same height have different tips, or OFFLINE if a peer is down            |

### `tests/test_blockchain.py`: unit tests

The tests cover:

- Part 1: known Bitcoin test vectors (private key `1` gives `1BgGZ9…`/`KwDiBf…`), Base58 round-trips, the handout's example address, the prefix rule, and the submitted `keypair.json`.
- Part 2: the genesis fields and hash, the exact hash input format, and that the optimised miner equals the reference hash.
- Part 3: rejection of tampered, low-difficulty, wrong-parent and malformed blocks, and same-height (fork) rejection.

### `scripts/fork_demo.sh`

Sends `POST /mine` to Node2 and Node3 at the same instant with `curl`, waits for both, then prints the three nodes' tips. It is a backup for the fork demo in case typing `mine` in two terminals isn't fast enough.

---

## 5. Running the nodes

Start all three nodes before mining, each in its own terminal (commands in §1). The chain is kept in memory only, so restarting a node resets it to the genesis block. Startup output:

```
[+] Loading keypair from keypair.json... (Found existing match)
[+] Public Address : 1LuCB6yU1yVrkewvVh5q2bQumHpckTPHPw
[+] Prefix Status  : MATCH FOUND ("LuC" matches "LUC" case-insensitive)
[+] Node Identity initialized successfully.
[+] Node1 listening on http://127.0.0.1:8001
[+] Peers: http://127.0.0.1:8002, http://127.0.0.1:8003
[+] Difficulty: 4 leading hex zeros
[+] Genesis hash: 7d8d1860463148c8a5bf939cc167a063d9d0618b2c5df0f79eac033e36f02904
```

Config file format (`node1.json`):

```json
{ "node_id": "Node1", "port": 8001, "peers": ["http://127.0.0.1:8002", "http://127.0.0.1:8003"] }
```

### Console commands

| Command         | Action                                                                              |
| --------------- | ----------------------------------------------------------------------------------- |
| `msg <text>`    | add a pending text message (stays local to this node)                               |
| `pending`       | list pending messages                                                               |
| `mine`          | mine one block (pending messages, or `[]`), append locally, broadcast, stop         |
| `chain`         | print the local chain                                                               |
| `block <n>`     | print block _n_ as JSON                                                             |
| `status`        | node id, address, height, tip, difficulty                                           |
| `peers`         | height and tip of every node, and a **FORK** flag if tips at the same height differ |
| `help` / `quit` |                                                                                     |

### HTTP API (each node, ports 8001–8003)

| Method & path   | Body                                  | Purpose                                                                     |
| --------------- | ------------------------------------- | --------------------------------------------------------------------------- |
| `GET /status`   |                                       | node summary                                                                |
| `GET /chain`    |                                       | full chain as JSON                                                          |
| `GET /pending`  |                                       | pending messages                                                            |
| `POST /message` | `{"text": "hello"}`                   | add a pending message                                                       |
| `POST /mine`    |                                       | mine one block now; returns the block                                       |
| `POST /block`   | `{"block": {...}, "sender": "Node1"}` | peer-to-peer: receive a block (200 accepted / 409 rejected / 400 malformed) |

```bash
curl -X POST localhost:8001/message -d '{"text":"hello"}'
curl -X POST localhost:8001/mine
curl localhost:8002/chain
```

## 6. Block hashing: exact field order and format

The `hash` field is **not** part of the hash input. The hash input is this UTF-8 string:

```
{index}|{timestamp}|{prev_hash}|{data_json}|{nonce}|{miner_address}
```

| #   | Field           | Formatting                                                                                                          |
| --- | --------------- | ------------------------------------------------------------------------------------------------------------------- |
| 1   | `index`         | decimal integer, no padding (`1`)                                                                                   |
| 2   | `timestamp`     | ISO-8601 UTC with microseconds (`2026-10-18T19:11:44.482913Z`); genesis keeps `2026-01-01T00:00:00Z`                |
| 3   | `prev_hash`     | 64 lowercase hex characters                                                                                         |
| 4   | `data`          | compact JSON array: `json.dumps(data, separators=(",", ":"), ensure_ascii=False)`, e.g. `["hello","world"]` or `[]` |
| 5   | `nonce`         | decimal integer, no padding                                                                                         |
| 6   | `miner_address` | Base58 P2PKH address (`GENESIS` for block 0)                                                                        |

The six fields are joined with `|`, and the block hash is `SHA-256(UTF-8 bytes)` as a lowercase hex string:

```python
preimage = f"{index}|{timestamp}|{prev_hash}|{json.dumps(data, separators=(',', ':'), ensure_ascii=False)}|{nonce}|{miner_address}"
block_hash = hashlib.sha256(preimage.encode("utf-8")).hexdigest()
```

`data` is encoded as JSON so the input stays unambiguous even when a message contains `|`.

Genesis block example. It is hardcoded and identical on every node, and it is not checked for PoW:

```
0|2026-01-01T00:00:00Z|0000000000000000000000000000000000000000000000000000000000000000|["Genesis Block"]|0|GENESIS
→ 7d8d1860463148c8a5bf939cc167a063d9d0618b2c5df0f79eac033e36f02904
```

**Proof-of-Work:** the miner tries nonce values 0, 1, 2, … until the hex hash starts with `difficulty` zeros. Each extra zero means 16× more work on average: the default 4 (`"0000"`) needs about 65k tries (well under a second), and `--difficulty 6` about 16.7M tries (≈7 s at ~2.5 MH/s, but the time varies a lot from block to block). The miner hashes the constant part of the input once and reuses that SHA-256 state for every nonce; the result is byte-for-byte the formula above.

## 7. Validation & consensus

When a node receives `POST /block`, it first parses the block strictly. Missing fields or wrong types return **400**. It then runs **all four checks** and logs `PASS`/`FAIL` for each:

1. **Hash Verification:** recompute the hash from the six payload fields; it must equal `block.hash`.
2. **Difficulty Verification:** the recomputed hash starts with `"0" * difficulty`.
3. **Chain Continuity:** `block.prev_hash == local_tip.hash`.
4. **Index Sequence:** `block.index == local_tip.index + 1`.

The block is appended only if all four checks pass. Validation and append happen atomically under the chain lock.

**First-Valid-Block-Wins:** a node keeps the first valid block it sees for each height. A second, different block at the same height fails checks 3 and 4 and is rejected with `CONFLICT at height h … -> FORK`. Nodes never switch chains (see §3.5). If a peer is offline, the node logs `[WARN] Peer … unreachable … Continuing without it.` and carries on.

## 8. Demo script (15-minute slot)

**Step 1: launch.** Use the three commands in §1. Each node shows its `1LuC…` address with `MATCH FOUND`.

**Step 2: on-demand mining.**

```
Node1> msg Hello from Node1
Node1> mine
```

Node2 and Node3 each print the four checks as `[PASS]`, then `Block #1 ACCEPTED`. Run `peers` on any node to confirm all three agree.

**Step 3: fork.** `quit` all three nodes and restart them with `--difficulty 6`. That takes about 7 s per block on average, sometimes much shorter or longer. Then trigger mining on both at once:

```
Node2> mine          (and immediately)          Node3> mine
```

You can also run `../scripts/fork_demo.sh` from `src/` to send both `/mine` requests at the same instant. The expected output:

- One of Node2/Node3 logs `Received Block #1 … while mining - queued`. When its own mining finishes, it rejects the other block: `CONFLICT at height 1 … -> FORK`.
- Node1 accepts whichever block reached it first and rejects the other.
- `peers` prints `[!] FORK: nodes at the same height disagree on the tip block.`

If one node finished before the other had even started, there's no fork. Just trigger both again (or use `--difficulty 7`).

**Step 4: viva.** Hashing is in §6 and `blockchain.py`, HTTP routing in §5 and `node.start_server`, and validation in §7 and `blockchain.validate_block` / `node.receive_block`.

## 9. Tests

```bash
python3 -m unittest discover -s tests -v     # from the repository root
```

Expected ending: `Ran 15 tests in ...s` followed by `OK`.
