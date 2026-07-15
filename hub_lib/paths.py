"""Path logic for the hub: locate the hub root and classify paths.

Used by hooks (policy enforcement, impact tracking) and workflows (I/O). Pure
functions over ``pathlib.Path`` — no side effects, no third-party deps.
"""

from __future__ import annotations

from pathlib import Path

# Marker files/dirs that only exist at the hub root.
_ROOT_MARKERS = ("CLAUDE.md", "workflows", "hub_lib")

DOCS_DIRNAME = "docs"
WORKSPACE_DIRNAME = "workspace"

# Subtrees under docs/ that are not hand-curated knowledge (skip during validation).
_CURATED_SKIP = {"generated", "memory", "superpowers"}


def find_hub_root(start: Path | str) -> Path:
    """Walk upward from *start* until the hub root markers are all present."""
    here = Path(start).resolve()
    for candidate in (here, *here.parents):
        if all((candidate / m).exists() for m in _ROOT_MARKERS):
            return candidate
    raise FileNotFoundError(f"hub root not found above {here}")


def docs_dir(hub_root: Path) -> Path:
    return hub_root / DOCS_DIRNAME


def generated_dir(hub_root: Path) -> Path:
    return hub_root / DOCS_DIRNAME / "generated"


def memory_dir(hub_root: Path) -> Path:
    return hub_root / DOCS_DIRNAME / "memory"


def workspace_dir(hub_root: Path) -> Path:
    return hub_root / WORKSPACE_DIRNAME


def _is_under(path: Path | str, base: Path) -> bool:
    try:
        Path(path).resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def is_workspace_path(path: Path | str, hub_root: Path) -> bool:
    """True if *path* is inside the pristine ``workspace/`` mirror."""
    return _is_under(path, workspace_dir(hub_root))


def is_generated_doc(path: Path | str, hub_root: Path) -> bool:
    """True if *path* is inside ``docs/generated/`` (regenerated, never hand-edited)."""
    return _is_under(path, generated_dir(hub_root))


def is_worktree_path(path: Path | str) -> bool:
    """True if *path* is inside a git worktree checkout (feature work is allowed)."""
    return ".claude/worktrees/" in Path(path).as_posix()


def iter_curated_docs(hub_root: Path):
    """Yield hand-curated ``.md`` docs (skips generated/, memory/, superpowers/)."""
    docs = docs_dir(hub_root)
    if not docs.exists():
        return
    for path in sorted(docs.rglob("*.md")):
        rel = path.relative_to(docs)
        if rel.parts and rel.parts[0] in _CURATED_SKIP:
            continue
        yield path


def map_source_to_docs(source_path: str, entries: list[dict]) -> list[str]:
    """Return docs whose declared ``source_paths`` cover *source_path*.

    *entries* come from ``docs/generated/source-map.json``; each is
    ``{"doc": "docs/…", "source_paths": ["workspace/…", …]}``. A declared path
    matches when it is a prefix of (or equal to) the changed path.
    """
    changed = Path(source_path).as_posix()
    hits: list[str] = []
    for entry in entries:
        for declared in entry.get("source_paths", []):
            decl = Path(declared).as_posix().rstrip("/")
            if changed == decl or changed.startswith(decl + "/"):
                hits.append(entry["doc"])
                break
    return hits
