package main

import (
	"encoding/json"
	"os"
)

type Keypair struct {
	PrivateKeyHex string `json:"private_key"`
	PublicKeyHex  string `json:"public_key"`
	Address       string `json:"address"`
}

func saveKeypair(path string, keypair Keypair) error {
	data, jsonErr := json.MarshalIndent(keypair, "", "    ")
	if jsonErr != nil {
		return jsonErr
	}
	return os.WriteFile(path, data, 0o600)
}

func loadKeypair(path string) (Keypair, error) {
	var keypair Keypair
	data, readErr := os.ReadFile(path)
	if readErr != nil {
		return keypair, readErr
	}
	jsonErr := json.Unmarshal(data, &keypair)
	if jsonErr != nil {
		return keypair, jsonErr
	}
	return keypair, nil
}