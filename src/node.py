"""
Part 3 - P2P node: HTTP API, block broadcast, receive-side validation.

HTTP routes (JSON in / JSON out):
  GET  /status    node id, address, height, tip hash, pending count, mining flag
  GET  /chain     full local chain
  GET  /pending   local pending messages
  POST /message   {"text": "..."}         add a pending message (stays local)
  POST /mine      mine one block now, append locally, broadcast, return it
  POST /block     {"block": {...}, "sender": "Node1"}   receive a peer's block

Concurrency model
-----------------
* The HTTP server is a ThreadingHTTPServer: every request runs on its own thread.
* `chain.lock` guards the block list (short critical sections only).
* `mining_lock` is held for a whole mining cycle (snapshot tip -> PoW -> append).
  A block arriving from a peer also takes `mining_lock`, so it is processed only
  after any local mining cycle has finished. The local miner is never interrupted.

  Consequence (intended for the A1 fork demo): if Node2 and Node3 mine the same
  height at overlapping times, each appends its *own* block first, then rejects
  the other's block as a same-height conflict -> First-Valid-Block-Wins fork.
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from blockchain import Block, Blockchain, mine_block

PEER_TIMEOUT_SECONDS = 600  # peer may be busy mining at high difficulty before it answers


class Console:
    """Thread-safe printing that keeps the interactive prompt intact."""

    def __init__(self, prompt: str):
        self.prompt = prompt
        self.prompt_visible = False
        self._lock = threading.Lock()
        self._tty = sys.stdout.isatty()

    def log(self, msg: str = ""):
        with self._lock:
            if self.prompt_visible and self._tty:
                sys.stdout.write("\r\033[K")  # wipe the half-drawn prompt line
            sys.stdout.write(msg + "\n")
            if self.prompt_visible and self._tty:
                sys.stdout.write(self.prompt)
            sys.stdout.flush()


class Node:
    def __init__(self, config: dict, identity: dict, difficulty: int, console: Console):
        self.node_id = config["node_id"]
        self.host = config.get("host", "127.0.0.1")
        self.port = int(config["port"])
        self.peers = [p.rstrip("/") for p in config.get("peers", [])]
        self.address = identity["address"]
        self.difficulty = difficulty
        self.console = console
        self.log = console.log

        self.chain = Blockchain()
        self.pending = []
        self.pending_lock = threading.Lock()
        self.mining_lock = threading.Lock()
        self.is_mining = False
        self.server = None

    # ------------------------------------------------------------------ #
    # Pending messages
    # ------------------------------------------------------------------ #
    def add_message(self, text: str) -> int:
        with self.pending_lock:
            self.pending.append(text)
            return len(self.pending)

    def pending_snapshot(self) -> list:
        with self.pending_lock:
            return list(self.pending)

    # ------------------------------------------------------------------ #
    # Mining on command
    # ------------------------------------------------------------------ #
    def mine(self):
        """One full mining cycle. Returns the mined Block, or None if already mining."""
        if not self.mining_lock.acquire(blocking=False):
            self.log(f"[!] {self.node_id} is busy (already mining or processing a block). Try again shortly.")
            return None
        try:
            self.is_mining = True
            tip = self.chain.tip
            data = self.pending_snapshot()
            index = tip.index + 1
            target = "0" * self.difficulty

            self.log(f"[+] Triggering Mining Cycle on {self.node_id}...")
            self.log(f"[+] Block #{index} Target Difficulty: {self.difficulty} leading zeros (\"{target}...\")")
            self.log(f"[+] Parent: #{tip.index} {tip.hash[:16]}... | Data: {json.dumps(data, ensure_ascii=False)}")

            def progress(nonce, digest, elapsed):
                rate = f" ({nonce / elapsed:,.0f} H/s)" if elapsed > 0.5 else ""
                self.log(f"[+] Nonce: {nonce:<10} -> Hash: {digest}{rate}")

            block, elapsed = mine_block(index, tip.hash, data, self.address, self.difficulty, on_progress=progress)
            self.log(f"[+] Block #{block.index} Mined! Nonce: {block.nonce} ({elapsed:.2f}s)")
            self.log(f"[+] Block Hash: {block.hash}")
            self.log(f"[+] Miner: {block.miner_address}")

            # Local chain update BEFORE broadcasting. Incoming blocks wait on
            # mining_lock, so our tip cannot have moved underneath us.
            ok, checks, reason = self.chain.try_append(block, self.difficulty)
            if not ok:
                self.log(f"[!] Own block #{block.index} could not be appended: {reason}")
                return None
            with self.pending_lock:
                # Remove exactly the messages that went into the block
                self.pending = self.pending[len(data):]
            self.log(f"[+] Block #{block.index} appended to local chain. Local height: {self.chain.height}")
        finally:
            self.is_mining = False
            self.mining_lock.release()

        self.broadcast(block)
        return block

    # ------------------------------------------------------------------ #
    # Broadcasting (direct connections, no gossip/re-forwarding)
    # ------------------------------------------------------------------ #
    def broadcast(self, block: Block, wait: bool = False):
        if not self.peers:
            self.log("[!] No peers configured; nothing to broadcast.")
            return
        self.log(f"[+] Broadcasting Block #{block.index} to {len(self.peers)} peer(s)...")
        payload = json.dumps({"block": block.to_dict(), "sender": self.node_id}).encode("utf-8")
        threads = [threading.Thread(target=self._send_block, args=(peer, payload, block), daemon=True)
                   for peer in self.peers]
        for t in threads:
            t.start()
        if wait:
            for t in threads:
                t.join()

    def _send_block(self, peer: str, payload: bytes, block: Block):
        req = urllib.request.Request(peer + "/block", data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=PEER_TIMEOUT_SECONDS) as resp:
                body = json.loads(resp.read() or b"{}")
                self.log(f"[+] Peer {body.get('node_id', peer)} ACCEPTED Block #{block.index}")
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read() or b"{}")
            except ValueError:
                body = {}
            who = body.get("node_id", peer)
            self.log(f"[!] Peer {who} REJECTED Block #{block.index}: {body.get('reason', e.reason)}")
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)
            self.log(f"[WARN] Peer {peer} unreachable ({reason}). Continuing without it.")

    # ------------------------------------------------------------------ #
    # Receiving a block from a peer
    # ------------------------------------------------------------------ #
    def receive_block(self, block_dict: dict, sender: str):
        """Validate and (maybe) append a peer's block. Returns (status_code, response_dict)."""
        try:
            block = Block.from_dict(block_dict)
        except (ValueError, TypeError) as e:
            self.log(f"[!] Malformed block from {sender}: {e}")
            return 400, {"accepted": False, "reason": f"malformed block: {e}"}

        if not self.mining_lock.acquire(blocking=False):
            self.log(f"[~] Received Block #{block.index} from {sender} while mining - "
                     f"queued until our mining cycle completes.")
            self.mining_lock.acquire()
        try:
            self.log(f"[+] Received Block #{block.index} from {sender} (hash {block.hash[:16]}..., "
                     f"miner {block.miner_address})")
            ok, checks, reason = self.chain.try_append(block, self.difficulty)
            for i, (name, passed, detail) in enumerate(checks, 1):
                self.log(f"    [{'PASS' if passed else 'FAIL'}] {i}. {name}: {detail}")
            if ok:
                self.log(f"[+] Block #{block.index} ACCEPTED and appended. Local height: {self.chain.height}")
                return 200, {"accepted": True, "height": self.chain.height}
            self.log(f"[!] Block #{block.index} from {sender} REJECTED: {reason}")
            if "FORK" in reason:
                self.log(f"[!] FORK: our tip is {self.chain.tip.short()} - not yielding (First-Valid-Block-Wins).")
            return 409, {"accepted": False, "reason": reason,
                         "checks": [{"check": n, "passed": p, "detail": d} for n, p, d in checks]}
        finally:
            self.mining_lock.release()

    # ------------------------------------------------------------------ #
    # Status helpers
    # ------------------------------------------------------------------ #
    def status(self) -> dict:
        tip = self.chain.tip
        return {
            "node_id": self.node_id,
            "address": self.address,
            "port": self.port,
            "difficulty": self.difficulty,
            "height": tip.index,
            "tip_hash": tip.hash,
            "tip_miner": tip.miner_address,
            "pending": len(self.pending_snapshot()),
            "mining": self.is_mining,
            "peers": self.peers,
        }

    def fetch_peer_status(self, peer: str, timeout: float = 3.0):
        try:
            with urllib.request.urlopen(peer + "/status", timeout=timeout) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"error": str(getattr(e, "reason", e))}

    # ------------------------------------------------------------------ #
    # HTTP server
    # ------------------------------------------------------------------ #
    def start_server(self):
        node = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"ECE496Node/{node.node_id}"

            def log_message(self, fmt, *args):  # silence default access log
                pass

            def _send(self, code, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json(self):
                length = int(self.headers.get("Content-Length") or 0)
                if length == 0:
                    return {}
                return json.loads(self.rfile.read(length).decode("utf-8"))

            def do_GET(self):
                path = self.path.split("?")[0].rstrip("/") or "/"
                if path in ("/", "/status"):
                    self._send(200, node.status())
                elif path == "/chain":
                    chain = node.chain.snapshot()
                    self._send(200, {"node_id": node.node_id, "length": len(chain),
                                     "chain": [b.to_dict() for b in chain]})
                elif path == "/pending":
                    self._send(200, {"node_id": node.node_id, "pending": node.pending_snapshot()})
                else:
                    self._send(404, {"error": f"unknown route {path}"})

            def do_POST(self):
                path = self.path.split("?")[0].rstrip("/")
                try:
                    body = self._read_json()
                except (ValueError, UnicodeDecodeError):
                    self._send(400, {"error": "invalid JSON body"})
                    return
                if not isinstance(body, dict):
                    self._send(400, {"error": "JSON body must be an object"})
                    return

                if path == "/block":
                    sender = str(body.get("sender") or self.client_address[0])
                    code, resp = node.receive_block(body.get("block"), sender)
                    self._send(code, {"node_id": node.node_id, **resp})
                elif path == "/message":
                    text = body.get("text", body.get("message"))
                    if not isinstance(text, str) or not text.strip():
                        self._send(400, {"error": "provide {\"text\": \"...\"}"})
                        return
                    count = node.add_message(text)
                    node.log(f"[+] Message added via HTTP: {text!r} ({count} pending)")
                    self._send(200, {"node_id": node.node_id, "pending": count})
                elif path == "/mine":
                    node.log("[+] /mine requested via HTTP")
                    block = node.mine()
                    if block is None:
                        self._send(409, {"node_id": node.node_id, "error": "busy - already mining"})
                    else:
                        self._send(200, {"node_id": node.node_id, "block": block.to_dict()})
                else:
                    self._send(404, {"error": f"unknown route {path}"})

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def shutdown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
