# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""source_map.py — derive docs/generated/source-map.json from front matter.

Scans every curated doc's ``source_paths`` and records which doc covers which
source path. The PostToolUse hook and /update-project-docs use this to map an
edited file to the docs it may affect.

    uv run workflows/source_map.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import frontmatter, paths  # noqa: E402


def build_entries(hub_root: Path) -> list[dict]:
    entries: list[dict] = []
    for doc in paths.iter_curated_docs(hub_root):
        meta, _ = frontmatter.load(doc)
        sources = meta.get("source_paths") or []
        if not sources:
            continue
        entries.append(
            {
                "doc": doc.relative_to(hub_root).as_posix(),
                "title": meta.get("title", ""),
                "type": meta.get("type", ""),
                "source_paths": sources,
            }
        )
    return entries


def write_map(hub_root: Path, entries: list[dict]) -> Path:
    target = paths.generated_dir(hub_root) / "source-map.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_by": "workflows/source_map.py",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "complete": True,
        "entries": entries,
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    hub_root = paths.find_hub_root(Path.cwd())
    entries = build_entries(hub_root)
    target = write_map(hub_root, entries)
    print(
        f"source map: {len(entries)} doc(s) with source_paths -> {target.relative_to(hub_root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
