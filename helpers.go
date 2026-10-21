package main

func isOnlyAlphabet(s string) bool {
	for _, r := range s {
		if r < 'A' || r > 'Z' {
			return false
		}
	}
	return true
}
