"""
One-time vanity key generation (Part 1). Run this BEFORE the demo; the nodes
then simply load keypair.json.

    python3 keygen.py --name "Lucius Lechner"       # derives the prefix (LUC)
    python3 keygen.py --vanity-prefix LUC            # or give it directly
"""

import argparse
import os
import sys

from wallet import load_keypair, matches_prefix, normalize_prefix, prefix_from_name, save_keypair, search_vanity

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description="Generate a Legacy Bitcoin vanity keypair")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--vanity-prefix", help="3 letters, e.g. LUC")
    group.add_argument("--name", help='full name, e.g. "Lucius Lechner" (prefix rule applied)')
    parser.add_argument("--out", default=os.path.join(HERE, "keypair.json"))
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="overwrite an existing keypair.json")
    args = parser.parse_args()

    if args.name:
        first, _, last = args.name.strip().partition(" ")
        prefix = prefix_from_name(first, last)
    else:
        prefix = normalize_prefix(args.vanity_prefix)

    if os.path.exists(args.out) and not args.force:
        existing = load_keypair(args.out)
        if matches_prefix(existing["address"], prefix):
            print(f"[+] {args.out} already holds a matching address: {existing['address']}")
            return
        print(f"[!] {args.out} exists with a different prefix ({existing['address']}). Use --force.")
        sys.exit(1)

    keypair = search_vanity(prefix, workers=args.workers)
    save_keypair(keypair, args.out)
    stats = keypair["search_stats"]
    print(f"[+] MATCH FOUND after {stats['addresses_tried']:,} addresses in {stats['seconds']}s")
    print(f"[+] Address     : {keypair['address']}")
    print(f"[+] Public key  : {keypair['public_key_compressed_hex']}")
    print(f"[+] Saved to    : {args.out}")
    print("[!] Assignment use only - never send real funds to this address.")


if __name__ == "__main__":
    main()
