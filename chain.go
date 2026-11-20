package main

import (
	"fmt"
	"strings"
	"time"
)

func meetsDifficulty(hash string, difficulty int) bool {
	return strings.HasPrefix(hash, strings.Repeat("0", difficulty))
}

func mineBlock(tip Block, data []string, miner string, difficulty int) Block {
	b := Block{
		Index:        tip.Index + 1,
		Timestamp:    time.Now().UTC().Format(time.RFC3339),
		PrevHash:     tip.Hash,
		Data:         data,
		MinerAddress: miner,
	}

	fmt.Printf("[+] Block #%d Target Difficulty: %d leading zeros (%q)\n",
		b.Index, difficulty, strings.Repeat("0", difficulty)+"...")
	for {
		b.Hash = b.computeHash()
		found := meetsDifficulty(b.Hash, difficulty)

		if b.Nonce%100000 == 0 || found {
			fmt.Printf("[+] Nonce: %-6d -> Hash: %s\n", b.Nonce, b.Hash)
		}
		if found {
			return b
		}

		b.Nonce++
	}
}

func validateBlock(b Block, tip Block, difficulty int) error {
	if b.computeHash() != b.Hash {
		return fmt.Errorf("hash mismatch")
	}
	if !meetsDifficulty(b.Hash, difficulty) {
		return fmt.Errorf("insufficient difficulty")
	}
	if b.PrevHash != tip.Hash {
		return fmt.Errorf("prev_hash mismatch")
	}
	if b.Index != tip.Index+1 {
		return fmt.Errorf("index mismatch")
	}
	return nil
}
