package main

import (
	"encoding/json"
	"fmt"
	"strings"
)

type Block struct {
	Index        int      `json:"index"`
	PrevHash     string   `json:"prev_hash"`
	Timestamp    string   `json:"timestamp"`
	Data         []string `json:"data"`
	Nonce        uint64   `json:"nonce"`
	MinerAddress string   `json:"miner_address"`
	Hash         string   `json:"hash"`
}

func genesisBlock() Block {
	return Block{
		Index:        0,
		PrevHash:     strings.Repeat("0", 64),
		Timestamp:    "",
		Data:         []string{"Genesis Block"},
		Nonce:        0,
		MinerAddress: "GENESIS",
		Hash:         strings.Repeat("0", 64),
	}
}

func (b Block) computeHash() string {
	return ""
}

func (b Block) hashInput() string {
	data, _ := json.Marshal(b.Data)
	return fmt.Sprintf("%d|%s|%s|%s|%d|%s", b.Index, b.PrevHash, b.Timestamp, data, b.Nonce, b.MinerAddress)
}
