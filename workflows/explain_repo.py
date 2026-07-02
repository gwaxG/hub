# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""explain_repo.py — deterministic half of the /explain-repo capability.

The hub is Python-only: this script owns discovery, mirror-tree creation, and
index building. The per-repo LLM analysis (writing each repo's markdown doc) is
done by Agent subagents dispatched from the `explain-repo` skill — not here.

Subcommands:
    plan <target> [--force]   Discover every git repo under workspace/<target>
                              (a single repo dir, a group dir, or "" for the whole
                              workspace). Pre-creates the mirrored doc directories
                              under docs/workspace_graph/ and prints a JSON plan the
                              skill feeds to the analysis agents. Repos whose doc
                              already exists are skipped unless --force.

    index                     (Re)build docs/workspace_graph/index.md from the
                              per-repo docs already written (reads their frontmatter
                              title/language + the ## Purpose line). Deterministic.

Usage:
    uv run workflows/explain_repo.py plan skillcorner/software/skcr-utils
    uv run workflows/explain_repo.py plan skillcorner/applications --force
    uv run workflows/explain_repo.py index
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = REPO_ROOT / "workspace"
DOCS_ROOT = REPO_ROOT / "docs" / "workspace_graph"


def _find_repos(base: Path) -> list[Path]:
    """Every git repo (dir containing a .git) at or under base."""
    out = subprocess.run(
        ["find", str(base), "-type", "d", "-name", ".git"],
        capture_output=True, text=True,
    ).stdout.split()
    return sorted(Path(p).parent for p in out)


def plan(target: str, force: bool) -> int:
    base = (WORKSPACE / target).resolve() if target else WORKSPACE.resolve()
    # Safety: never escape the workspace.
    if base != WORKSPACE.resolve() and not base.is_relative_to(WORKSPACE.resolve()):
        print(json.dumps({"error": f"target escapes workspace/: {target}"}))
        return 1
    if not base.exists():
        print(json.dumps({"error": f"path not found under workspace/: {target}"}))
        return 1

    repos, skipped = [], []
    for rd in _find_repos(base):
        rel = rd.relative_to(WORKSPACE).as_posix()          # skillcorner/shared/skcr-utils
        doc = DOCS_ROOT / f"{rel}.md"
        if doc.exists() and not force:
            skipped.append(rel)
            continue
        doc.parent.mkdir(parents=True, exist_ok=True)         # pre-create mirror dirs
        repos.append({
            "name": rd.name,
            "group": rel.rsplit("/", 1)[0] if "/" in rel else "",
            "relPath": rel,
            "repoPath": str(rd),
            "docPath": str(doc),
        })

    print(json.dumps({
        "generated": date.today().isoformat(),
        "docsRoot": str(DOCS_ROOT),
        "indexPath": str(DOCS_ROOT / "index.md"),
        "repos": repos,
        "skipped": skipped,
    }, indent=2))
    return 0


def _frontmatter(text: str) -> dict[str, str]:
    """Parse the leading --- ... --- block into a flat str->str dict."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def _purpose(text: str) -> str:
    """First non-empty line under the '## Purpose' heading."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "## purpose":
            for nxt in lines[i + 1:]:
                s = nxt.strip()
                if s.startswith("## "):
                    break
                if s:
                    return s
            break
    return ""


def build_index() -> int:
    if not DOCS_ROOT.exists():
        print("No docs/workspace_graph/ yet — nothing to index.", file=sys.stderr)
        return 1
    docs = sorted(p for p in DOCS_ROOT.rglob("*.md") if p.name != "index.md")
    entries = []
    for p in docs:
        rel = p.relative_to(DOCS_ROOT).with_suffix("").as_posix()   # skillcorner/shared/skcr-utils
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = _frontmatter(text)
        entries.append({
            "name": rel.rsplit("/", 1)[-1],
            "group": rel.rsplit("/", 1)[0] if "/" in rel else "(root)",
            "rel": rel,
            "language": fm.get("language", "") or _lang_from_tags(fm.get("tags", "")),
            "purpose": _purpose(text),
        })

    groups: dict[str, list[dict]] = {}
    for e in entries:
        groups.setdefault(e["group"], []).append(e)

    today = date.today().isoformat()
    out = [
        "---",
        "type: source",
        "title: workspace-graph index",
        f"generated: {today}",
        "tags: [index, workspace, repos]",
        "---",
        "# Workspace Graph — Repo Index",
        "",
        f"Generated {today}. {len(entries)} repo(s) documented across "
        f"{len(groups)} group(s). Each entry links to its per-repo doc, "
        "mirroring the `workspace/` tree.",
        "",
    ]
    for g in sorted(groups):
        rows = sorted(groups[g], key=lambda e: e["name"])
        out += [f"## {g}", "", "| Repo | Language | Purpose |", "| --- | --- | --- |"]
        for e in rows:
            purpose = e["purpose"].replace("|", "\\|")
            out.append(f"| [{e['name']}](./{e['rel']}.md) | {e['language'] or '?'} | {purpose} |")
        out.append("")

    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    (DOCS_ROOT / "index.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {DOCS_ROOT / 'index.md'} ({len(entries)} repos, {len(groups)} groups).")
    return 0


def _lang_from_tags(tags: str) -> str:
    """tags frontmatter looks like '[repo, group, python]'; last token is language."""
    inner = tags.strip().lstrip("[").rstrip("]")
    parts = [t.strip() for t in inner.split(",") if t.strip()]
    return parts[-1] if parts else ""


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "plan":
        rest = argv[1:]
        force = "--force" in rest
        rest = [a for a in rest if a != "--force"]
        target = rest[0] if rest else ""
        return plan(target, force)
    if cmd == "index":
        return build_index()
    print(f"unknown command: {cmd} (use: plan | index)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
