package main

import (
	"bufio"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"

	"github.com/btcsuite/btcd/btcec/v2"
)

func main() {
	var prefix string
	var configPath string
	var difficulty int
	var err error
	var address string
	var priv *btcec.PrivateKey

	flag.StringVar(&configPath, "config", "node1.json", "Path to the node config")
	flag.StringVar(&prefix, "vanity-prefix", "LUC", "Vanity prefix for the Bitcoin address")
	flag.IntVar(&difficulty, "difficulty", 4, "Leading hex zeros for PoW")
	flag.Parse()

	prefix = strings.ToUpper(prefix)
	if len(prefix) != 3 || !isOnlyAlphabet(prefix) {
		log.Fatalf("invalid vanity prefix: %q. must be 3 letters A-Z.", prefix)
	}

	config, err := loadConfig(configPath)
	if err != nil {
		log.Fatal(err)
	}
	// fmt.Printf("[+] %s listening on port %d, peers: %v\n", config.NodeID, config.Port, config.Peers)

	if difficulty < 1 || difficulty > 8 {
		log.Fatalf("difficulty must be 1-8, got %d", difficulty)
	}

	keypair, err := loadKeypair("keypair.json")

	if errors.Is(err, os.ErrNotExist) {
		fmt.Printf("[+] No keypair.json found, searching for prefix %q...\n", prefix)

		attempts := 0

		for {
			priv, err = btcec.NewPrivateKey()
			if err != nil {
				log.Fatal(err)
			}

			address = addressFromPubKey(priv.PubKey().SerializeCompressed())
			attempts++

			if matchesVanity(address, prefix) {
				break
			}
		}

		privBytes := priv.Serialize()
		pubBytes := priv.PubKey().SerializeCompressed()

		fmt.Printf("[+] Found match after %d attempts, saved to keypair.json\n", attempts)

		keypair = Keypair{
			PrivateKeyHex: hex.EncodeToString(privBytes),
			PublicKeyHex:  hex.EncodeToString(pubBytes),
			Address:       address,
		}

		err = saveKeypair("keypair.json", keypair)
		if err != nil {
			log.Fatal(err)
		}
	} else if err != nil {
		log.Fatal(err)
	} else {
		fmt.Println("[+] Loading keypair from keypair.json... (Found existing match)")
	}

	privBytes, err := hex.DecodeString(keypair.PrivateKeyHex)
	if err != nil {
		log.Fatal(err)
	}
	_, pub := btcec.PrivKeyFromBytes(privBytes)
	if addressFromPubKey(pub.SerializeCompressed()) != keypair.Address {
		log.Fatal("keypair.json: address does not match private key")
	}
	if !matchesVanity(keypair.Address, prefix) {
		log.Fatalf("keypair.json address %s does not match prefix %q", keypair.Address, prefix)
	}

	fmt.Println("[+] Public Address :", keypair.Address)
	fmt.Printf("[+] Prefix Status : MATCH FOUND (%q matches %q case-insensitive)\n", keypair.Address[1:4], prefix)
	fmt.Println("[+] Node Identity initialized successfully.")
	fmt.Printf("[+] Mining Difficulty : %d leading zeros (%q)\n", difficulty, strings.Repeat("0", difficulty)+"...")

	node := newNode(config, keypair.Address, difficulty)

	fmt.Println("[+] Genesis Hash :", node.Chain[0].Hash)
	http.HandleFunc("/block", node.handleBlock)

	addr := fmt.Sprintf(":%d", config.Port)
	fmt.Printf("[+] %s listening on %s, peers: %v\n", config.NodeID, addr, config.Peers)

	go func() {
		log.Fatal(http.ListenAndServe(addr, nil))
	}()

	scanner := bufio.NewScanner(os.Stdin)
	for {
		fmt.Print(config.NodeID + "> ")
		if !scanner.Scan() {
			break
		}
		line := strings.TrimSpace(scanner.Text())

		if text, ok := strings.CutPrefix(line, "msg "); ok {
			node.addMessage(text)
			continue
		}

		switch line {
		case "":
		case "mine":
			b := node.mine()
			node.broadcast(b)
		case "chain":
			node.printChain()
		case "msg":
			fmt.Println("[*] Usage: msg <text>")
		case "exit":
			return
		default:
			fmt.Println("[-] Unknown command:", line)
		}
	}
	err = scanner.Err()
	if err != nil {
		log.Fatal(err)
	}
}
