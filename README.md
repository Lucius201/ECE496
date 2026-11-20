# ECE 496C / 519C Assignment 1: Go Blockchain

A small blockchain in Go: a Bitcoin vanity address (prefix `LUC`), proof-of-work mining on command, and 3 nodes that talk over HTTP.

## Setup

Needs Go 1.27 or newer.

```
go mod download
```

## Run the 3 nodes

Open 3 terminals in this folder and run one command in each:

```
go run . --config node1.json --vanity-prefix LUC --difficulty 4
go run . --config node2.json --vanity-prefix LUC --difficulty 4
go run . --config node3.json --vanity-prefix LUC --difficulty 4
```

Start all 3 nodes before mining. The chain is kept in memory only, so restarting a node resets it to the genesis block.

Each node loads the vanity keypair from `keypair.json` (address `1LUCJAyam1a4MYxzTty148eF3j7QZMHDQb`). If the file is missing, a new one is searched for and saved.

| Flag              | Default      | Meaning                                                                    |
| ----------------- | ------------ | -------------------------------------------------------------------------- |
| `--config`        | `node1.json` | Node config (node id, port, peers)                                         |
| `--vanity-prefix` | `LUC`        | 3 letters that characters 2-4 of the address must match (case-insensitive) |
| `--difficulty`    | `4`          | Number of leading hex zeros a block hash needs (1-8)                       |

Ports: Node1 = 8001, Node2 = 8002, Node3 = 8003.

## Commands (type into a node's terminal)

| Command      | What it does                                                                      |
| ------------ | --------------------------------------------------------------------------------- |
| `msg <text>` | Add a pending message (stays on this node)                                        |
| `mine`       | Mine a block with the pending messages, add it to the chain, send it to the peers |
| `chain`      | Print this node's chain                                                           |
| `exit`       | Stop the node                                                                     |

Peers receive blocks at `POST /block`. A block is only added if it passes all four checks:

1. The recomputed hash equals the block's `hash`
2. The hash has the required number of leading zeros
3. `prev_hash` equals the hash of the current tip
4. `index` equals the tip's index + 1

## Block hashing

The `hash` field is not part of the hash input. The fields are joined with `|` in this order and hashed once with SHA-256 (output as lowercase hex):

```
index|timestamp|prev_hash|data|nonce|miner_address
```

Go format string: `fmt.Sprintf("%d|%s|%s|%s|%d|%s", index, timestamp, prev_hash, data, nonce, miner_address)`

- `index` and `nonce`: decimal numbers
- `timestamp`: UTC, RFC 3339, e.g. `2026-01-01T00:00:00Z`
- `data`: the message list as JSON, e.g. `["a","b"]`, or `[]` when there are no messages

Genesis block (hardcoded, same on every node):

```
input: 0|2026-01-01T00:00:00Z|0000000000000000000000000000000000000000000000000000000000000000|["Genesis Block"]|0|GENESIS
hash:  7d8d1860463148c8a5bf939cc167a063d9d0618b2c5df0f79eac033e36f02904
```
