# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""clone_repos.py — mirror every project under a set of GitLab groups locally.

For every project found under the configured groups (recursing into subgroups):
  - not cloned yet          -> git clone into DEST_DIR/<full/namespace/path>
  - already cloned, clean   -> checkout `main` (or repo default) + git pull --ff-only
  - already cloned, dirty   -> SKIP (never touch a tree with uncommitted changes)
                               and report it at the end.

Config is HARDCODED below (groups + destination). The GitLab token is read from
the GITLAB_TOKEN environment variable so a PAT never lands in this tracked file
(the hub rule: connector auth lives outside the repo).

Usage:
    GITLAB_TOKEN=glpat-... uv run workflows/clone_repos.py
    GITLAB_TOKEN=glpat-... uv run workflows/clone_repos.py --dry-run
    GITLAB_TOKEN=glpat-... uv run workflows/clone_repos.py --dest ./workspace
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Hardcoded config
# ---------------------------------------------------------------------------
GITLAB_HOST = "https://gitlab.com"
GROUPS = [
    "skillcorner/devops",
    "skillcorner/data-engineering",
    "skillcorner/applications",
    "skillcorner/shared",
    "skillcorner/software",
]
DEST_DIR = (
    Path(__file__).resolve().parent.parent / "workspace"
)  # inside the hub; never write outside it
PREFERRED_BRANCH = "main"  # checked out on update when it exists; else repo default
SKIP_ARCHIVED = True

PER_PAGE = 100
TIMEOUT = 30


# ---------------------------------------------------------------------------
# GitLab API
# ---------------------------------------------------------------------------
def list_projects(group: str, token: str) -> list[dict]:
    """Return all (non-archived, unless SKIP_ARCHIVED is False) projects under a
    group, recursing into subgroups. Paginates the GitLab API."""
    enc = requests.utils.quote(group, safe="")
    url = f"{GITLAB_HOST}/api/v4/groups/{enc}/projects"
    headers = {"PRIVATE-TOKEN": token}
    params = {
        "include_subgroups": "true",
        "per_page": PER_PAGE,
        "archived": "false" if SKIP_ARCHIVED else None,
        "page": 1,
    }
    projects: list[dict] = []
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        projects.extend(batch)
        next_page = resp.headers.get("X-Next-Page")
        if not next_page:
            break
        params["page"] = int(next_page)
    return projects


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------
def auth_args(token: str) -> list[str]:
    """`-c http.extraHeader=...` so clone/fetch/pull authenticate WITHOUT the
    token ever being persisted into the repo's .git/config remote URL."""
    b64 = base64.b64encode(f"oauth2:{token}".encode()).decode()
    return ["-c", f"http.extraHeader=Authorization: Basic {b64}"]


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def is_dirty(repo: Path) -> bool:
    """True if the working tree has staged or unstaged changes (untracked files
    are ignored — they don't block a pull)."""
    rc, out, _ = run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"]
    )
    return rc != 0 or bool(out)


def target_branch(repo: Path, default_branch: str) -> str:
    """Prefer PREFERRED_BRANCH when it exists on origin, else the repo default."""
    rc, _, _ = run(
        [
            "git",
            "-C",
            str(repo),
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/remotes/origin/{PREFERRED_BRANCH}",
        ]
    )
    if rc == 0:
        return PREFERRED_BRANCH
    rc, out, _ = run(
        ["git", "-C", str(repo), "symbolic-ref", "refs/remotes/origin/HEAD"]
    )
    if rc == 0 and out:
        return out.rsplit("/", 1)[-1]
    return default_branch or PREFERRED_BRANCH


# ---------------------------------------------------------------------------
# Per-project handling
# ---------------------------------------------------------------------------
def handle_project(
    project: dict, dest_root: Path, token: str, dry_run: bool
) -> tuple[str, str]:
    """Clone or update one project. Returns (category, message)."""
    ns_path = project["path_with_namespace"]  # e.g. skillcorner/devops/foo
    clean_url = project["http_url_to_repo"]
    default_branch = project.get("default_branch") or PREFERRED_BRANCH
    local = dest_root / ns_path

    if not (local / ".git").exists():
        if local.exists() and any(local.iterdir()):
            return (
                "error",
                f"{ns_path}: destination exists but is not a git repo — skipped",
            )
        if dry_run:
            return "cloned", f"{ns_path}: would clone -> {local}"
        local.parent.mkdir(parents=True, exist_ok=True)
        rc, _, err = run(["git", *auth_args(token), "clone", clean_url, str(local)])
        if rc != 0:
            return (
                "error",
                f"{ns_path}: clone failed — {err.splitlines()[-1] if err else 'unknown'}",
            )
        branch = target_branch(local, default_branch)
        run(["git", "-C", str(local), "checkout", branch])
        return "cloned", f"{ns_path}: cloned ({branch})"

    # Already present.
    if is_dirty(local):
        return "skipped", ns_path
    if dry_run:
        return "updated", f"{ns_path}: would fetch + checkout + pull"

    rc, _, err = run(["git", *auth_args(token), "-C", str(local), "fetch", "--prune"])
    if rc != 0:
        return (
            "error",
            f"{ns_path}: fetch failed — {err.splitlines()[-1] if err else 'unknown'}",
        )
    branch = target_branch(local, default_branch)
    rc, _, err = run(["git", "-C", str(local), "checkout", branch])
    if rc != 0:
        return (
            "error",
            f"{ns_path}: checkout {branch} failed — {err.splitlines()[-1] if err else 'unknown'}",
        )
    rc, _, err = run(["git", *auth_args(token), "-C", str(local), "pull", "--ff-only"])
    if rc != 0:
        return (
            "error",
            f"{ns_path}: pull failed ({branch}) — {err.splitlines()[-1] if err else 'unknown'}",
        )
    return "updated", f"{ns_path}: updated ({branch})"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest", type=Path, default=DEST_DIR, help=f"clone root (default {DEST_DIR})"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report actions without touching disk"
    )
    args = parser.parse_args(argv)

    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        print(
            "ERROR: set GITLAB_TOKEN in the environment (a GitLab PAT with read_api + read_repository).",
            file=sys.stderr,
        )
        return 2

    dest_root = args.dest.expanduser().resolve()
    print(f"Destination : {dest_root}")
    print(f"Groups      : {', '.join(GROUPS)}")
    if args.dry_run:
        print("Mode        : DRY RUN (no changes)")
    print()

    # Discover every project across all groups (dedup by namespace path).
    seen: dict[str, dict] = {}
    for group in GROUPS:
        try:
            found = list_projects(group, token)
        except requests.HTTPError as e:
            print(f"  group {group}: API error — {e}")
            continue
        for p in found:
            seen[p["path_with_namespace"]] = p
        print(f"  {group}: {len(found)} project(s)")
    projects = sorted(seen.values(), key=lambda p: p["path_with_namespace"])
    print(f"\nTotal unique projects: {len(projects)}\n")

    buckets: dict[str, list[str]] = {
        "cloned": [],
        "updated": [],
        "skipped": [],
        "error": [],
    }
    total = len(projects)
    width = len(str(total))
    for i, p in enumerate(projects, 1):
        ns_path = p["path_with_namespace"]
        verb = "would process" if args.dry_run else "processing"
        # Live progress: announce the current repo BEFORE the (possibly slow) git op.
        print(f"  [{i:>{width}}/{total}] {verb}: {ns_path} ...", flush=True)
        category, msg = handle_project(p, dest_root, token, args.dry_run)
        buckets[category].append(msg)
        marker = {"cloned": "+", "updated": "^", "skipped": "!", "error": "x"}[category]
        print(f"           [{marker}] {msg}", flush=True)

    # Summary.
    print("\n" + "=" * 60)
    print(f"cloned  : {len(buckets['cloned'])}")
    print(f"updated : {len(buckets['updated'])}")
    print(f"skipped : {len(buckets['skipped'])} (uncommitted changes)")
    print(f"errors  : {len(buckets['error'])}")

    if buckets["skipped"]:
        print("\nSKIPPED — local changes present, left untouched:")
        for ns in buckets["skipped"]:
            print(f"  - {ns}")
    if buckets["error"]:
        print("\nERRORS:")
        for m in buckets["error"]:
            print(f"  - {m}")

    return 1 if buckets["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
