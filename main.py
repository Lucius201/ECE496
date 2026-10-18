"""
Launcher so the handout's command also works from the repository root:

    python3 main.py --config node1.json --vanity-prefix LUC --difficulty 4

It simply runs src/main.py (where all the code lives). node1.json and
keypair.json are found in src/ automatically.
"""

import os
import runpy
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
sys.path.insert(0, SRC)
runpy.run_path(os.path.join(SRC, "main.py"), run_name="__main__")
