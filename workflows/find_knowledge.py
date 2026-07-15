# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""find_knowledge.py — deterministic ranked search across the curated vault.

Thin CLI over ``hub_lib.search`` (shared with the UserPromptSubmit hook). An
agent can rank the shortlist semantically afterwards.

    uv run workflows/find_knowledge.py match state machine [--type workflow] [--limit 10]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import paths, search  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="+")
    parser.add_argument("--type")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    hub_root = paths.find_hub_root(Path.cwd())
    terms = [t.lower() for t in args.query]
    results = search.search(hub_root, terms, args.type, args.limit)

    if not results:
        print(f"no matches for {' '.join(args.query)!r}")
        return 0
    for s, rel, title, snip in results:
        print(f"[{s:>3}] {rel} — {title}")
        if snip:
            print(f"       {snip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
