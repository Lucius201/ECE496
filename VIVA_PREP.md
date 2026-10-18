# Viva prep (personal – not part of the submission zip)

## Likely questions and short answers

**Why compressed public keys? What are the 0x02 and 0x03 bytes?**
For any `x` there are two possible `y` values, `y` and `p − y`, and exactly one of them is even. So 1 byte of parity plus the 32-byte `x` is enough to recover the point: 33 bytes instead of 65.

**Why RIPEMD160(SHA256(pk))?**
It makes the address shorter (20 bytes) and adds a layer of defence: the address does not reveal the public key until the coins are spent. Using two different hash designs also guards against a weakness in either one.

**What does the checksum protect against?**
Typos. `SHA256(SHA256(0x00‖hash160))[:4]` means a random typo is caught with a probability of 1 − 2⁻³².

**Why does every address start with '1'?**
Base58 writes each leading `0x00` byte as `'1'`, and the version byte is `0x00`.

**Why case-insensitive?**
Base58 has no `0`, `O`, `I` or `l`. Example: an `L` can only appear uppercase, because `l` is excluded.

**Why are letters R–Z slow?**
The value after the 0x00 byte is below 2¹⁹². When that 24-byte number is written in base 58, its leading digit can only go up to index ~22 (`'Q'`). Uppercase R–Z therefore never appear in position 2, and the lowercase forms only show up in the rarer 33-character addresses (~4%).

**How does your vanity search work?**
Each process takes a random k and walks forward: `Q ← Q + G`. That is one point addition per key instead of a full scalar multiplication. Multiprocessing gets around the GIL.

**Exact hash input?**
`index|timestamp|prev_hash|data_json|nonce|miner_address`, UTF-8 encoded, then SHA-256, then lowercase hex (see `blockchain.hash_preimage`). The `hash` field is excluded. Why JSON for `data`? Without it, `["a|b"]` and `["a","b"]` would produce the same string.

**Expected work at difficulty d?**
16^d hashes on average. d=4 is ≈65k, d=6 is ≈16.7M; at ~2.5 MH/s that is ≈7 s. Each extra hex zero means 16× more work.

**How is the miner fast in Python?**
The fixed prefix is hashed once, and `hashlib` state `.copy()` is used for each nonce, so only the nonce and suffix get hashed each time.

**HTTP routing?**
`ThreadingHTTPServer` runs one thread per request. `do_GET`/`do_POST` dispatch on the path. A broadcast sends to each peer from its own thread using `urllib`. `HTTPError` 409 means a peer rejected the block. `URLError`/`ConnectionRefused` means the peer is offline, which gets a warning and no crash.

**Thread safety?**
`chain.lock` (RLock) makes validate+append atomic. `mining_lock` makes sure only one mining cycle runs at a time, and queues incoming blocks until that cycle ends.

**Why a fork happens and why it persists:**
Both miners build on the same tip. Each appends its own block first, so the other block fails check 3 (`prev_hash != tip`) and check 4 (`index != tip+1`). First-Valid-Block-Wins never replaces a block, so neither side gives way. **The fix (A2):** keep side branches and switch to the chain with the most total work. A node that is behind also needs a way to sync.

**What if a block arrives for height tip+2?**
It is rejected as "ahead of our chain". A1 has no chain sync.

**Weaknesses/attacks?**

- Timestamps are not validated.
- Difficulty is set per node, not agreed by consensus.
- Any node with a valid PoW can claim any `miner_address`, because blocks are not signed. Signing them with the secp256k1 key would fix this.
- There is no Sybil or DoS protection.
- The chain is in memory only.

## Pre-demo checklist

- [ ] `python3 -m unittest discover -s tests -v` passes
- [ ] Ports 8001–8003 are free (`lsof -i :8001`)
- [ ] 3 terminals open in `src/`; commands copied from README §3
- [ ] Practise the fork at `--difficulty 6`; `scripts/fork_demo.sh` as a backup
- [ ] Read through `blockchain.py` and `node.receive_block` once more
