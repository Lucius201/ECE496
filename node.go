package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"
)

type Node struct {
	Mutex      sync.Mutex
	Config     Config
	Address    string
	Difficulty int
	Chain      []Block
	Pending    []string
}

func newNode(config Config, address string, difficulty int) *Node {
	return &Node{Mutex: sync.Mutex{}, Config: config, Address: address, Difficulty: difficulty, Chain: []Block{genesisBlock()}, Pending: []string{}}
}

func (n *Node) addMessage(msg string) {
	n.Mutex.Lock()
	defer n.Mutex.Unlock()

	n.Pending = append(n.Pending, msg)
	fmt.Printf("[+] Message queued: %q (%d pending)\n", msg, len(n.Pending))
}

func (n *Node) mine() Block {
	n.Mutex.Lock()
	defer n.Mutex.Unlock()

	fmt.Println("[+] Triggering Mining Cycle on " + n.Config.NodeID + "...")
	tip := n.Chain[len(n.Chain)-1]
	newBlock := mineBlock(tip, n.Pending, n.Address, n.Difficulty)
	n.Chain = append(n.Chain, newBlock)
	n.Pending = []string{}

	fmt.Printf("[+] Block #%d Mined! Nonce: %d\n", newBlock.Index, newBlock.Nonce)
	fmt.Println("[+] Block Hash:", newBlock.Hash)
	fmt.Println("[+] Miner:", newBlock.MinerAddress)
	return newBlock
}

func (n *Node) printChain() {
	n.Mutex.Lock()
	defer n.Mutex.Unlock()

	for _, b := range n.Chain {
		fmt.Printf("[#%d] hash=%s prev=%s nonce=%d time=%s data=%q\n",
			b.Index, b.Hash[:16], b.PrevHash[:16], b.Nonce, b.Timestamp, b.Data)
	}
}

func (n *Node) receiveBlock(b Block) error {
	n.Mutex.Lock()
	defer n.Mutex.Unlock()

	tip := n.Chain[len(n.Chain)-1]
	err := validateBlock(b, tip, n.Difficulty)
	if err != nil {
		fmt.Printf("\n[-] Block #%d rejected: %v\n", b.Index, err)
		return err
	}

	n.Chain = append(n.Chain, b)

	fmt.Printf("\n[+] Block #%d accepted (hash %s, prev %s)\n", b.Index, b.Hash[:16], b.PrevHash[:16])
	return nil
}

func (n *Node) broadcast(b Block) {
	body, err := json.Marshal(b)
	if err != nil {
		fmt.Printf("[!] Could not encode block #%d: %v\n", b.Index, err)
		return
	}
	client := &http.Client{Timeout: 60 * time.Second}

	for _, peer := range n.Config.Peers {
		go func(peer string) {
			response, err := client.Post(peer+"/block", "application/json", bytes.NewReader(body))

			if err != nil {
				fmt.Printf("\n[!] Peer %s unreachable: %v (continuing)\n", peer, err)
				return
			}

			defer response.Body.Close()

			if response.StatusCode != http.StatusOK {
				fmt.Printf("\n[-] Peer %s rejected block #%d (status %d)\n", peer, b.Index, response.StatusCode)
				return

			} else {
				fmt.Printf("\n[+] Block #%d sent to %s", b.Index, peer)
			}
		}(peer)
	}
}
