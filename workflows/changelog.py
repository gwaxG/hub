# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""changelog.py — deterministic half of the /changelog capability.

The hub is Python-only: this script owns git-diffing every workspace repo
against a persisted per-repo SHA snapshot, writing CHANGELOG.md, allocating ADR
numbers, and advancing the state. The LLM work (classifying each repo's change
and authoring the doc update / ADR body) is done by Agent subagents dispatched
from the `changelog` skill — not here.

Because /clone-repos does `git pull --ff-only`, the old HEAD is gone by the time
we look. So the watcher keeps its OWN state: data/changelog_state.json maps each
repo (relative to workspace/) to its last-seen commit SHA. Each run diffs the
current HEAD against the stored SHA to get exactly the new commits.

Subcommands:
    plan [target] [--since-baseline]
        Discover every git repo under workspace/<target> (empty = whole
        workspace) and, per repo, compute the new commits since the stored SHA.
        Prints a JSON plan the skill fans out over. Does NOT mutate state.
        First ever run (no state file): records current HEADs as the baseline
        and reports {"baseline": true, "repos": []}.

    record --plan <plan.json> --results <results.json>
        The commit step. Appends a dated section to CHANGELOG.md, writes any
        ADRs (numbers assigned here to avoid collisions), and advances the state
        file to the new HEAD SHAs. `results.json` is the skill's collected agent
        output: a list of {relPath, category, summary, docUpdated, adr?}.

Usage:
    uv run workflows/changelog.py plan
    uv run workflows/changelog.py plan skillcorner/software
    uv run workflows/changelog.py record --plan plan.json --results results.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = REPO_ROOT / "workspace"
DOCS_ROOT = REPO_ROOT / "docs" / "workspace_graph"
ADR_ROOT = REPO_ROOT / "docs" / "adr"
STATE_FILE = REPO_ROOT / "data" / "changelog_state.json"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

MAX_COMMITS = 30  # commits listed per repo in the plan (cap for token budget)
MAX_CHANGED_FILES = 40  # changed files listed per repo in the plan
VALID_CATEGORIES = ("routine", "notable", "architectural")


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> str:
    """Run a read-only git command in `repo`; return stripped stdout ('' on error)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _find_repos(base: Path) -> list[Path]:
    """Every git repo (dir containing a .git) at or under base."""
    out = subprocess.run(
        ["find", str(base), "-type", "d", "-name", ".git"],
        capture_output=True,
        text=True,
    ).stdout.split()
    return sorted(Path(p).parent for p in out)


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def _commits(repo: Path, old: str, new: str) -> list[dict[str, str]]:
    """Subjects of commits in (old, new], newest first, capped at MAX_COMMITS."""
    raw = _git(
        repo,
        "log",
        "--no-merges",
        f"--max-count={MAX_COMMITS}",
        "--pretty=format:%h\x1f%s",
        f"{old}..{new}",
    )
    commits = []
    for line in raw.splitlines():
        if "\x1f" in line:
            sha, subject = line.split("\x1f", 1)
            commits.append({"sha": sha, "subject": subject})
    return commits


def _diffstat(repo: Path, old: str, new: str) -> dict[str, int]:
    """Files/insertions/deletions summary for old..new."""
    raw = _git(repo, "diff", "--shortstat", f"{old}..{new}")

    # e.g. " 7 files changed, 120 insertions(+), 30 deletions(-)"
    def _n(pattern: str) -> int:
        m = re.search(pattern, raw)
        return int(m.group(1)) if m else 0

    return {
        "files": _n(r"(\d+) files? changed"),
        "insertions": _n(r"(\d+) insertions?\(\+\)"),
        "deletions": _n(r"(\d+) deletions?\(-\)"),
    }


def _changed_files(repo: Path, old: str, new: str) -> list[str]:
    raw = _git(repo, "diff", "--name-only", f"{old}..{new}")
    files = [f for f in raw.splitlines() if f]
    return files[:MAX_CHANGED_FILES]


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------
def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
def plan(target: str, since_baseline: bool) -> int:
    base = (WORKSPACE / target).resolve() if target else WORKSPACE.resolve()
    if base != WORKSPACE.resolve() and not base.is_relative_to(WORKSPACE.resolve()):
        print(json.dumps({"error": f"target escapes workspace/: {target}"}))
        return 1
    if not base.exists():
        print(json.dumps({"error": f"path not found under workspace/: {target}"}))
        return 1

    state = _load_state()
    tracked: dict = state.get("repos", {})
    first_run = not tracked

    repos_found = _find_repos(base)

    # First ever run: seed the baseline for the WHOLE workspace and report nothing.
    if first_run and not since_baseline:
        seeded = {}
        for rd in _find_repos(WORKSPACE):
            rel = rd.relative_to(WORKSPACE).as_posix()
            head = _head(rd)
            if head:
                seeded[rel] = {"sha": head, "updated": date.today().isoformat()}
        _save_state({"generated": date.today().isoformat(), "repos": seeded})
        print(
            json.dumps(
                {
                    "generated": date.today().isoformat(),
                    "baseline": True,
                    "seeded": len(seeded),
                    "repos": [],
                },
                indent=2,
            )
        )
        return 0

    changed: list[dict] = []
    unchanged = 0
    new_repos: list[str] = []  # cloned since last run — seeded, not reported
    seed_shas: dict[str, str] = {}  # relPath -> sha to seed at record time

    for rd in repos_found:
        rel = rd.relative_to(WORKSPACE).as_posix()
        head = _head(rd)
        if not head:
            continue
        stored = tracked.get(rel, {}).get("sha")

        if stored is None:
            # New repo: seed its SHA (document via /explain-repo, not the changelog)
            # unless --since-baseline, in which case report from the root commit.
            if since_baseline:
                stored = _git(rd, "rev-list", "--max-parents=0", "HEAD").split("\n")[0]
                if not stored:
                    seed_shas[rel] = head
                    new_repos.append(rel)
                    continue
            else:
                seed_shas[rel] = head
                new_repos.append(rel)
                continue

        if stored == head:
            unchanged += 1
            continue

        doc = DOCS_ROOT / f"{rel}.md"
        changed.append(
            {
                "name": rd.name,
                "group": rel.rsplit("/", 1)[0] if "/" in rel else "",
                "relPath": rel,
                "repoPath": str(rd),
                "docPath": str(doc),
                "docExists": doc.exists(),
                "oldSha": stored,
                "newSha": head,
                "commitCount": len(_commits(rd, stored, head)),
                "commits": _commits(rd, stored, head),
                "diffstat": _diffstat(rd, stored, head),
                "changedFiles": _changed_files(rd, stored, head),
            }
        )

    print(
        json.dumps(
            {
                "generated": date.today().isoformat(),
                "baseline": False,
                "target": target or "(whole workspace)",
                "changed": changed,
                "unchangedCount": unchanged,
                "newRepos": new_repos,
                "seedShas": seed_shas,
                "repos": changed,  # alias so the skill can read either key
            },
            indent=2,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "decision"


def _next_adr_number() -> int:
    ADR_ROOT.mkdir(parents=True, exist_ok=True)
    nums = []
    for p in ADR_ROOT.glob("*.md"):
        m = re.match(r"(\d+)", p.name)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def _ensure_changelog_header() -> str:
    if CHANGELOG.exists():
        return CHANGELOG.read_text(encoding="utf-8")
    return (
        "# Changelog\n\n"
        "Workspace changes tracked by the `/changelog` skill. Newest first. Each "
        "run diffs every `workspace/` repo against the last-seen commit and records "
        "what changed, updating the `docs/` knowledge base for notable and "
        "architectural changes.\n"
    )


def _write_adr(number: int, title: str, body: str, rel: str, today: str) -> Path:
    path = ADR_ROOT / f"{number:04d}-{_slug(title)}.md"
    header = (
        f"# {number:04d}. {title}\n\n"
        f"- **Status:** proposed\n"
        f"- **Date:** {today}\n"
        f"- **Repo:** `workspace/{rel}`\n\n"
    )
    path.write_text(header + body.strip() + "\n", encoding="utf-8")
    return path


def record(plan_path: Path, results_path: Path) -> int:
    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    if isinstance(results, dict):
        results = results.get("results", results.get("repos", []))

    changed = {
        r["relPath"]: r for r in plan_data.get("changed", plan_data.get("repos", []))
    }
    today = date.today().isoformat()

    # ---- assign ADR numbers + write ADRs -----------------------------------
    next_num = _next_adr_number()
    adr_links: dict[str, str] = {}  # relPath -> "docs/adr/NNNN-...md"
    for res in results:
        adr = res.get("adr")
        if adr and adr.get("title") and adr.get("body"):
            path = _write_adr(
                next_num, adr["title"], adr["body"], res["relPath"], today
            )
            adr_links[res["relPath"]] = path.relative_to(REPO_ROOT).as_posix()
            next_num += 1

    # ---- build the dated CHANGELOG section ---------------------------------
    blocks: list[str] = []
    order = {"architectural": 0, "notable": 1, "routine": 2}
    for res in sorted(
        results, key=lambda r: order.get(r.get("category", "routine"), 3)
    ):
        rel = res["relPath"]
        info = changed.get(rel, {})
        category = res.get("category", "routine")
        summary = (res.get("summary") or "").strip()
        old, new = info.get("oldSha", "")[:7], info.get("newSha", "")[:7]
        count = info.get("commitCount", 0)

        heading = f"### {rel} — {category}"
        if rel in adr_links:
            heading += f" → [ADR]({adr_links[rel]})"
        elif res.get("docUpdated"):
            heading += " (doc updated)"

        line = f"{count} commit{'s' if count != 1 else ''}"
        if old and new:
            line += f" (`{old}`…`{new}`)"
        if summary:
            line += f". {summary}"

        block = [heading, "", line]
        commits = info.get("commits", [])[:8]
        if commits:
            block.append("")
            block += [f"- `{c['sha']}` {c['subject']}" for c in commits]
        blocks.append("\n".join(block))

    joined_blocks = "\n\n".join(blocks)

    # Insert newest-first. If the top section is already today's, append the new
    # blocks under it; otherwise open a new "## <today>" section above it.
    existing = _ensure_changelog_header()
    if joined_blocks:
        lines = existing.rstrip("\n").split("\n")
        first_section = next(
            (i for i, ln in enumerate(lines) if ln.startswith("## ")), len(lines)
        )
        head = "\n".join(lines[:first_section]).rstrip("\n")
        rest = "\n".join(lines[first_section:]).strip("\n")

        if rest.startswith(f"## {today}"):
            # Merge into today's existing section.
            rest_lines = rest.split("\n")
            next_section = next(
                (i for i, ln in enumerate(rest_lines[1:], 1) if ln.startswith("## ")),
                len(rest_lines),
            )
            todays = "\n".join(rest_lines[:next_section]).rstrip("\n")
            older = "\n".join(rest_lines[next_section:]).strip("\n")
            rest = todays + "\n\n" + joined_blocks
            if older:
                rest += "\n\n" + older
        else:
            new_section = f"## {today}\n\n" + joined_blocks
            rest = new_section + ("\n\n" + rest if rest else "")

        CHANGELOG.write_text(head + "\n\n" + rest + "\n", encoding="utf-8")

    # ---- advance state -----------------------------------------------------
    state = _load_state()
    state.setdefault("repos", {})
    for rel, info in changed.items():
        state["repos"][rel] = {"sha": info["newSha"], "updated": today}
    for rel, sha in plan_data.get("seedShas", {}).items():
        state["repos"][rel] = {"sha": sha, "updated": today}
    state["generated"] = today
    _save_state(state)

    n_adr = len(adr_links)
    n_doc = sum(1 for r in results if r.get("docUpdated"))
    print(
        json.dumps(
            {
                "recorded": len(results),
                "docsUpdated": n_doc,
                "adrsWritten": n_adr,
                "changelog": str(CHANGELOG),
                "stateAdvanced": len(changed) + len(plan_data.get("seedShas", {})),
            },
            indent=2,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_plan = sub.add_parser(
        "plan", help="diff workspace repos against the SHA snapshot"
    )
    p_plan.add_argument(
        "target",
        nargs="?",
        default="",
        help="repo/group path under workspace/ (default: all)",
    )
    p_plan.add_argument(
        "--since-baseline",
        action="store_true",
        help="report newly-cloned repos from their root commit instead of seeding",
    )

    p_rec = sub.add_parser("record", help="write CHANGELOG/ADRs and advance state")
    p_rec.add_argument(
        "--plan", type=Path, required=True, help="the plan.json emitted by `plan`"
    )
    p_rec.add_argument(
        "--results",
        type=Path,
        required=True,
        help="the skill's collected agent results",
    )

    args = parser.parse_args(argv)
    if args.cmd == "plan":
        return plan(args.target, args.since_baseline)
    if args.cmd == "record":
        return record(args.plan, args.results)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
