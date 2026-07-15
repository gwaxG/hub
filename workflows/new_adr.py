# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""new_adr.py — stamp a numbered Architecture Decision Record.

Finds the next NNNN number under docs/architecture/decisions/ and writes a
template ADR. The narrative (context, alternatives, consequences) is filled in
afterwards by the author / agent.

    uv run workflows/new_adr.py "Adopt Cognito JWT at the gateway" [--status proposed]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import paths  # noqa: E402

_NUM_RE = re.compile(r"^(\d{4})-")


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "decision"


def next_number(decisions_dir: Path) -> int:
    numbers = [
        int(m.group(1))
        for p in decisions_dir.glob("*.md")
        if (m := _NUM_RE.match(p.name))
    ]
    return (max(numbers) + 1) if numbers else 1


def template(number: int, title: str, status: str) -> str:
    return (
        "---\n"
        f"title: {number:04d} — {title}\n"
        "type: decision\n"
        f"status: {status}\n"
        "owners: []\n"
        "systems: []\n"
        "source_paths: []\n"
        "related: []\n"
        "last_verified: \n"
        "generated: false\n"
        "---\n\n"
        f"# {number:04d} — {title}\n\n"
        "## Context\n\nWhat forces are at play? Why is a decision needed now?\n\n"
        "## Decision\n\nWhat we are doing.\n\n"
        "## Alternatives considered\n\n- Option A — trade-offs\n- Option B — trade-offs\n\n"
        "## Consequences\n\nPositive, negative, and migration implications.\n\n"
        "## Status\n\n"
        f"{status.capitalize()}.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title")
    parser.add_argument(
        "--status",
        default="proposed",
        choices=["proposed", "draft", "current", "deprecated"],
    )
    args = parser.parse_args()

    hub_root = paths.find_hub_root(Path.cwd())
    decisions = paths.docs_dir(hub_root) / "architecture" / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)

    number = next_number(decisions)
    target = decisions / f"{number:04d}-{slugify(args.title)}.md"
    if target.exists():
        print(f"refusing to overwrite {target.relative_to(hub_root)}")
        return 1
    target.write_text(template(number, args.title, args.status), encoding="utf-8")
    print(f"created {target.relative_to(hub_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
