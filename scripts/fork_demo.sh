#!/usr/bin/env bash
# Fork demo helper: trigger /mine on Node2 and Node3 at the same instant.
# Start all three nodes with --difficulty 6 first (see README.md).
set -u
echo "[+] Triggering mine on Node2 and Node3 simultaneously..."
curl -s -m 600 -X POST http://127.0.0.1:8002/mine > /dev/null & p2=$!
curl -s -m 600 -X POST http://127.0.0.1:8003/mine > /dev/null & p3=$!
wait "$p2" "$p3"
sleep 1
echo "[+] Tips after the race:"
for port in 8001 8002 8003; do
  curl -s "http://127.0.0.1:$port/status" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('  %s: height=%s tip=%s...' % (d['node_id'], d['height'], d['tip_hash'][:24]))"
done
