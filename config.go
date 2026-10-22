package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

type Config struct {
	NodeID string   `json:"node_id"`
	Port   int      `json:"port"`
	Peers  []string `json:"peers"`
}

func loadConfig(path string) (Config, error) {
	var config Config
	data, readErr := os.ReadFile(path)
	if readErr != nil {
		return config, readErr
	}
	jsonErr := json.Unmarshal(data, &config)
	if jsonErr != nil {
		return config, jsonErr
	}
	for i := range config.Peers {
		config.Peers[i] = strings.TrimSpace(config.Peers[i])
	}
	if config.NodeID == "" || config.Port <= 0 || config.Port > 65535 || len(config.Peers) == 0 {
		return config, fmt.Errorf("%s: invalid node config (need node_id, port 1-65535, peers)", path)
	}
	return config, nil
}
