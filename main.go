package main

import (
	"encoding/hex"
	"fmt"
	"log"

	"github.com/btcsuite/btcd/btcec/v2"
)

func main() {
	prefix := "LUC"

	var priv *btcec.PrivateKey
	var address string
	var err error
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

	fmt.Println("attempts:", attempts)
	fmt.Println("private:", hex.EncodeToString(privBytes))
	fmt.Println("public:", hex.EncodeToString(pubBytes))
	fmt.Println("address:", address)

	keypair := Keypair{
		PrivateKeyHex: hex.EncodeToString(privBytes),
		PublicKeyHex:  hex.EncodeToString(pubBytes),
		Address:       address,
	}

	err = saveKeypair("keypair.json", keypair)
	if err != nil {
		log.Fatal(err)
	}
}
