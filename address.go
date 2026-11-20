package main

import (
	"crypto/sha256"
	"math/big"
	"strings"

	"golang.org/x/crypto/ripemd160"
)

const alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

func sha256Sum(b []byte) []byte {
	h := sha256.Sum256(b)
	return h[:]
}

func ripemd160Sum(b []byte) []byte {
	h := ripemd160.New()
	h.Write(b)
	return h.Sum(nil)
}

func hash160(b []byte) []byte {
	return ripemd160Sum(sha256Sum(b))
}

func base58Encode(input []byte) string {
	x := new(big.Int).SetBytes(input)
	base := big.NewInt(58)
	mod := new(big.Int)

	var out []byte
	for x.Sign() > 0 {
		x.DivMod(x, base, mod)
		out = append(out, alphabet[mod.Int64()])
	}

	for _, b := range input {
		if b != 0 {
			break
		}
		out = append(out, alphabet[0])
	}

	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return string(out)
}

func addressFromPubKey(pub []byte) string {
	pubKeyHash := hash160(pub)
	version := []byte{0x00}
	versioned := append(version, pubKeyHash...)
	checksum := sha256Sum(sha256Sum(versioned))[:4]
	payload := append(versioned, checksum...)
	return base58Encode(payload)
}

func matchesVanity(addr, prefix string) bool {
	if len(addr) < 1+len(prefix) {
		return false
	}
	return strings.EqualFold(addr[1:1+len(prefix)], prefix)
}
