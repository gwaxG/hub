# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""source_map.py — derive docs/generated/source-map.json from front matter.

Thin CLI over ``hub_lib.generate.build_source_map`` (shared with the MR hook).

    uv run workflows/source_map.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import generate, paths  # noqa: E402


def main() -> int:
    hub_root = paths.find_hub_root(Path.cwd())
    entries, target = generate.build_source_map(hub_root)
    print(
        f"source map: {len(entries)} doc(s) with source_paths -> {target.relative_to(hub_root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
