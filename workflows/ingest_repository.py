# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""ingest_repository.py — deterministic inventory of a workspace repo.

Owns the mechanical half of /ingest-repository: structure, languages, packages,
frameworks and entrypoints. Writes docs/generated/inventory-<repo>.json and prints
a summary the launching skill hands to Agent subagents for semantic analysis.

    uv run workflows/ingest_repository.py workspace/applications/wilson
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import paths  # noqa: E402

_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
_CODE_EXT = {".py", ".ts", ".js", ".go", ".rs", ".java", ".sql", ".yaml", ".yml", ".tf"}


def walk(repo: Path) -> tuple[Counter, list[str], set[str]]:
    ext_counts: Counter = Counter()
    all_names: set[str] = set()
    for path in repo.rglob("*"):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo).parts):
            continue
        if path.is_file():
            if path.suffix in _CODE_EXT:
                ext_counts[path.suffix] += 1
            all_names.add(path.name)
    top = sorted(
        p.name for p in repo.iterdir() if p.is_dir() and p.name not in _SKIP_DIRS
    )
    return ext_counts, top, all_names


def detect_frameworks(repo: Path, names: set[str]) -> list[str]:
    frameworks = []
    if "manage.py" in names:
        frameworks.append("django")
    dep_text = ""
    for dep_file in ("pyproject.toml", "requirements.txt", "setup.py"):
        f = repo / dep_file
        if f.exists():
            dep_text += f.read_text(encoding="utf-8", errors="replace").lower()
    if "fastapi" in dep_text:
        frameworks.append("fastapi")
    if "pulumi" in dep_text or (repo / "Pulumi.yaml").exists():
        frameworks.append("pulumi")
    return frameworks


def build_inventory(repo: Path) -> dict:
    ext_counts, top_dirs, names = walk(repo)
    return {
        "repo": repo.name,
        "top_level_dirs": top_dirs,
        "languages": dict(ext_counts.most_common()),
        "frameworks": detect_frameworks(repo, names),
        "has_tests": any(n in names for n in ("conftest.py",)) or "tests" in top_dirs,
        "has_readme": any(n.lower().startswith("readme") for n in names),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", help="path to a repo (usually under workspace/)")
    args = parser.parse_args()

    hub_root = paths.find_hub_root(Path.cwd())
    repo = (
        (hub_root / args.repo).resolve()
        if not Path(args.repo).is_absolute()
        else Path(args.repo)
    )
    if not repo.is_dir():
        print(f"not a directory: {repo}")
        return 1
    if not paths.is_workspace_path(repo, hub_root):
        print(f"warning: {repo} is outside the workspace/ mirror", file=sys.stderr)

    inventory = build_inventory(repo)
    inventory["generated_by"] = "workflows/ingest_repository.py"
    inventory["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inventory["source_path"] = (
        repo.relative_to(hub_root).as_posix()
        if paths.is_workspace_path(repo, hub_root)
        else str(repo)
    )

    target = paths.generated_dir(hub_root) / f"inventory-{repo.name}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    print(f"inventory -> {target.relative_to(hub_root)}")
    print(
        json.dumps(
            {
                k: inventory[k]
                for k in ("top_level_dirs", "languages", "frameworks", "has_tests")
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
