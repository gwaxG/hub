# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""find_knowledge.py — deterministic ranked search across the curated vault.

Scores each curated doc by query-term hits (title weighted heavily) and prints
the best matches with a snippet. An agent can rank the shortlist semantically
afterwards; this owns the deterministic retrieval.

    uv run workflows/find_knowledge.py match state machine [--type workflow] [--limit 10]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import frontmatter, paths  # noqa: E402

_TITLE_WEIGHT = 5


def score(terms: list[str], title: str, body: str) -> int:
    title_l, body_l = title.lower(), body.lower()
    return sum(_TITLE_WEIGHT * title_l.count(t) + body_l.count(t) for t in terms)


def snippet(terms: list[str], body: str) -> str:
    for line in body.splitlines():
        low = line.lower()
        if any(t in low for t in terms) and line.strip():
            return line.strip()[:120]
    return ""


def search(hub_root: Path, terms: list[str], type_filter: str | None):
    results = []
    for doc in paths.iter_curated_docs(hub_root):
        meta, body = frontmatter.load(doc)
        if type_filter and meta.get("type") != type_filter:
            continue
        title = meta.get("title", doc.stem)
        s = score(terms, title, body)
        if s:
            results.append(
                (s, doc.relative_to(hub_root).as_posix(), title, snippet(terms, body))
            )
    return sorted(results, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="+")
    parser.add_argument("--type")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    hub_root = paths.find_hub_root(Path.cwd())
    terms = [t.lower() for t in args.query]
    results = search(hub_root, terms, args.type)

    if not results:
        print(f"no matches for {' '.join(args.query)!r}")
        return 0
    for s, rel, title, snip in results[: args.limit]:
        print(f"[{s:>3}] {rel} — {title}")
        if snip:
            print(f"       {snip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
