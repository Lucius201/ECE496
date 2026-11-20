package main

import (
	"encoding/json"
	"net/http"
)

func (n *Node) handleBlock(w http.ResponseWriter, r *http.Request) {
	var b Block
	err := json.NewDecoder(r.Body).Decode(&b)
	if err != nil {
		http.Error(w, "bad block json", http.StatusBadRequest)
		return
	}
	err = n.receiveBlock(b)
	if err != nil {
		http.Error(w, err.Error(), http.StatusConflict)
		return
	}
	w.WriteHeader(http.StatusOK)
}
