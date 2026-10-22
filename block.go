package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
)

type Block struct {
	Index        int      `json:"index"`
	Timestamp    string   `json:"timestamp"`
	PrevHash     string   `json:"prev_hash"`
	Data         []string `json:"data"`
	Nonce        uint64   `json:"nonce"`
	MinerAddress string   `json:"miner_address"`
	Hash         string   `json:"hash"`
}

func genesisBlock() Block {
	g := Block{
		Index:        0,
		PrevHash:     strings.Repeat("0", 64),
		Timestamp:    "2026-01-01T00:00:00Z",
		Data:         []string{"Genesis Block"},
		Nonce:        0,
		MinerAddress: "GENESIS",
	}
	g.Hash = g.computeHash()
	return g
}

func (b Block) computeHash() string {
	h := sha256.Sum256([]byte(b.hashInput()))
	return hex.EncodeToString(h[:])
}

func (b Block) hashInput() string {
	data, _ := json.Marshal(b.Data)
	return fmt.Sprintf("%d|%s|%s|%s|%d|%s", b.Index, b.Timestamp, b.PrevHash, data, b.Nonce, b.MinerAddress)
}
