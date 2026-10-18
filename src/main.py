"""
ECE 496C / 519C - Assignment 1: lightweight Layer-1 blockchain node.

Usage:
    python3 main.py --config node1.json --vanity-prefix LUC --difficulty 4

Interactive commands: msg <text>, mine, chain, block <n>, pending, status,
peers, help, quit.
"""

import argparse
import json
import os
import sys
import threading

try:
    import readline  # noqa: F401 - enables arrow keys / command history in input()
except ImportError:  # e.g. Windows without pyreadline
    pass

from blockchain import DEFAULT_DIFFICULTY, GENESIS_BLOCK
from node import Console, Node
from wallet import load_keypair, matches_prefix, normalize_prefix, save_keypair, search_vanity

HERE = os.path.dirname(os.path.abspath(__file__))

HELP = """\
Commands:
  msg <text>     add a pending text message (local to this node)
  pending        show pending messages
  mine           mine one block with the pending messages and broadcast it
  chain          print this node's chain
  block <n>      print block n as JSON
  status         show this node's status
  peers          show every node's height / tip (spot forks)
  help           show this help
  quit           stop the node"""


def resolve_path(path: str) -> str:
    """Accept paths relative to the CWD or to this source directory."""
    if os.path.isabs(path) or os.path.exists(path):
        return path
    candidate = os.path.join(HERE, path)
    return candidate if os.path.exists(candidate) else path


def init_identity(prefix: str, keypair_path: str, allow_search: bool) -> dict:
    if os.path.exists(keypair_path):
        print(f"[+] Loading keypair from {os.path.basename(keypair_path)}...", end=" ")
        identity = load_keypair(keypair_path)
        if matches_prefix(identity["address"], prefix):
            print("(Found existing match)")
        else:
            print("(Prefix MISMATCH)")
            print(f"[!] {identity['address']} does not match '{prefix}'. "
                  f"Run 'python3 keygen.py --vanity-prefix {prefix} --force' to regenerate.")
            sys.exit(1)
    else:
        if not allow_search:
            print(f"[!] {keypair_path} not found. Run 'python3 keygen.py --vanity-prefix {prefix}' first.")
            sys.exit(1)
        print(f"[!] {os.path.basename(keypair_path)} not found - searching for a new vanity address.")
        identity = search_vanity(prefix)
        save_keypair(identity, keypair_path)
        print(f"[+] Saved keypair to {keypair_path}")

    found = identity["address"][1:4]
    print(f"[+] Public Address : {identity['address']}")
    print(f"[+] Prefix Status  : MATCH FOUND (\"{found}\" matches \"{prefix}\" case-insensitive)")
    print("[+] Node Identity initialized successfully.")
    return identity


def print_chain(node: Node):
    log = node.log
    for b in node.chain.snapshot():
        log(f"  #{b.index:<3} hash={b.hash[:20]}...  prev={b.prev_hash[:12]}...  nonce={b.nonce:<9} "
            f"time={b.timestamp}")
        log(f"        miner={b.miner_address}  data={json.dumps(b.data, ensure_ascii=False)}")


def print_peers(node: Node):
    rows = [node.status()] + [{**node.fetch_peer_status(p), "_url": p} for p in node.peers]
    tips = {}
    for r in rows:
        if "error" in r:
            node.log(f"  {r['_url']:<24} OFFLINE ({r['error']})")
            continue
        node.log(f"  {r['node_id']:<8} height={r['height']:<4} tip={r['tip_hash'][:20]}...  "
                 f"tip_miner={r['tip_miner']}{'  [mining]' if r.get('mining') else ''}")
        tips.setdefault(r["height"], set()).add(r["tip_hash"])
    if any(len(h) > 1 for h in tips.values()):
        node.log("  [!] FORK: nodes at the same height disagree on the tip block.")
    elif len(tips) > 1:
        node.log("  [~] Nodes are at different heights.")
    elif tips:
        node.log("  [+] All reachable nodes agree on the same tip.")


def repl(node: Node, console: Console):
    log = node.log
    log("Type 'help' for commands.")
    while True:
        console.prompt_visible = True
        try:
            line = input(console.prompt)
        except EOFError:
            # No interactive stdin (e.g. started in the background): keep serving HTTP.
            console.prompt_visible = False
            log("[~] stdin closed - running headless; use the HTTP endpoints.")
            threading.Event().wait()
        except KeyboardInterrupt:
            console.prompt_visible = False
            log("")
            return
        console.prompt_visible = False
        cmd, _, arg = line.strip().partition(" ")
        cmd = cmd.lower()
        if not cmd:
            continue
        if cmd == "msg":
            if not arg.strip():
                log("usage: msg <text>")
            else:
                count = node.add_message(arg.strip())
                log(f"[+] Message added ({count} pending)")
        elif cmd == "mine":
            node.mine()
        elif cmd == "pending":
            msgs = node.pending_snapshot()
            log(f"[+] {len(msgs)} pending: {json.dumps(msgs, ensure_ascii=False)}")
        elif cmd == "chain":
            print_chain(node)
        elif cmd == "block":
            chain = node.chain.snapshot()
            try:
                log(json.dumps(chain[int(arg)].to_dict(), indent=2, ensure_ascii=False))
            except (ValueError, IndexError):
                log(f"usage: block <0..{len(chain) - 1}>")
        elif cmd == "status":
            log(json.dumps(node.status(), indent=2))
        elif cmd == "peers":
            print_peers(node)
        elif cmd == "help":
            log(HELP)
        elif cmd in ("quit", "exit"):
            return
        else:
            log(f"unknown command '{cmd}' - type 'help'")


def main():
    parser = argparse.ArgumentParser(description="ECE 496C/519C A1 blockchain node")
    parser.add_argument("--config", required=True, help="node config JSON (node1.json, ...)")
    parser.add_argument("--vanity-prefix", required=True, help="3-letter vanity prefix, e.g. LUC")
    parser.add_argument("--difficulty", type=int, default=DEFAULT_DIFFICULTY,
                        help=f"leading hex zeros required (default {DEFAULT_DIFFICULTY})")
    parser.add_argument("--keypair", default="keypair.json", help="keypair file (default keypair.json)")
    parser.add_argument("--no-search", action="store_true",
                        help="fail instead of searching if keypair.json is missing")
    args = parser.parse_args()

    if not 1 <= args.difficulty <= 64:
        parser.error("--difficulty must be between 1 and 64")
    try:
        prefix = normalize_prefix(args.vanity_prefix)
    except ValueError as e:
        parser.error(str(e))

    config_path = resolve_path(args.config)
    with open(config_path, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    keypair_path = resolve_path(args.keypair)
    if not os.path.exists(keypair_path):
        keypair_path = os.path.join(HERE, args.keypair) if not os.path.isabs(args.keypair) else args.keypair
    identity = init_identity(prefix, keypair_path, allow_search=not args.no_search)

    console = Console(prompt=f"{config['node_id']}> ")
    node = Node(config, identity, args.difficulty, console)
    try:
        node.start_server()
    except OSError as e:
        print(f"[!] Could not bind {node.host}:{node.port}: {e}")
        sys.exit(1)

    print(f"[+] {node.node_id} listening on http://{node.host}:{node.port}")
    print(f"[+] Peers: {', '.join(node.peers) or '(none)'}")
    print(f"[+] Difficulty: {node.difficulty} leading hex zeros")
    print(f"[+] Genesis hash: {GENESIS_BLOCK.hash}")
    try:
        repl(node, console)
    finally:
        node.shutdown()
        print(f"[+] {node.node_id} stopped.")


if __name__ == "__main__":
    main()
