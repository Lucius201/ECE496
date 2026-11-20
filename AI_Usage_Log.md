# AI Usage Log

ECE 496C / 519C Blockchain Assignment 1 (Go implementation)

## Summary

|                  |                                                                                                                                           |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **AI tool**      | Claude (Anthropic)                                                                                                                        |
| **Used for**     | Explaining concepts, planning the file structure, small standalone Go examples, reviewing my code against the spec and known test vectors |
| **Not used for** | Writing the submitted source code.                                                                                                        |

I mainly used AI to turn what I already understood about Bitcoin into program logic. AI had the most input on the project structure: which files to create and what each should hold. And on reviewing code: solving syntax errors and helping with nicely formated prints.

## How I worked with the AI

1. **Ask about one concept** (e.g. RIPEMD-160 hashing in Go).
2. **Get a small standalone example** showing just that concept, with expected output, not the assignment code.
3. **Write the assignment code myself** using what I learned from the example.
4. **Ask for a review**: the AI read my code and compared it to the assignment PDF and known test vectors. Then I fixed the issues myself.

### AI Usage for Planning

| Prompt                                                   | AI output                                                                                                                                       | What I did with it                                                                                                                   |
| -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| How should I structure a Go project for this assignment? | Proposed splitting the code into one file per topic (identity, blocks, chain, networking, entry point) and a day-by-day plan up to the deadline | Kept the idea of one file per topic but chose my own split (`address.go`, `keypair.go`, `config.go`, `server.go`, `helpers.go`, ...) |
| Which libraries do I need?                               | Suggested `btcsuite/btcd/btcec/v2` for secp256k1 and `golang.org/x/crypto/ripemd160`, with everything else from the standard library            | Used both libraries; Base58 and the checksum are written by hand                                                                     |

### AI Usage for Coding

| Prompt                                                                           | AI output                                                                       | What I did with it                                 |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------- |
| How do I compute SHA-256 and RIPEMD-160 in Go?                                   | Small example of the hash functions with known outputs                          | Wrote Hash160 and checksum functions               |
| How do I generate a secp256k1 keypair with a public key in Go?                   | Example of `btcec` key generation and serialization                             | Used it in my key generation code                  |
| How does Base58 encoding work without a library?                                 | Explanation of the base conversion                                              | Implemented a Base58 encoder                       |
| How do I check characters 2-4 of the address against my prefix, ignoring case?   | Example using `strings.EqualFold`                                               | Wrote a prefix check for `LUC`                     |
| Is there a known private key and address to test my pipeline against?            | Test vector: private key `1` gives address `1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH` | Checked my pipeline against it                     |
| How do I try nonces until the hash has N leading zeros, and get a UTC timestamp? | Example of a nonce loop with a leading-zero check and RFC 3339 UTC timestamps   | Wrote a mining function and a progress output      |
| How do I read commands like `mine` and `msg <text>` from the terminal?           | Example using `bufio.Scanner` and `strings.CutPrefix`                           | Wrote a command loop, including `chain` and `exit` |

### AI Usage for Documentation

| Prompt                                       | AI output                                | What I did with it                              |
| -------------------------------------------- | ---------------------------------------- | ----------------------------------------------- |
| Turn my notes into a structured AI usage log | Turned my notes into this structured log | Checked every entry against what I actually did |
