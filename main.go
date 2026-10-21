package main

import (
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"log"
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
	keypair, err := loadKeypair("keypair.json")

	if errors.Is(err, os.ErrNotExist) {
		fmt.Println("[+] no keypair.json found")

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

		fmt.Println("[+] found:", attempts, "attempts")

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
		fmt.Println("[+] loading keypair from keypair.json")
	}

	privBytes, err := hex.DecodeString(keypair.PrivateKeyHex)
	if err != nil {
		log.Fatal(err)
	}
	_, pub := btcec.PrivKeyFromBytes(privBytes)
	if addressFromPubKey(pub.SerializeCompressed()) != keypair.Address {
		log.Fatal("keypair.json: address does not match private key")
	}

	fmt.Println("[+] address :", keypair.Address)
}
