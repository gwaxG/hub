---
name: hub-clone-repos
description: Clone or update every GitLab project under the skillcorner groups (devops, data-engineering, applications, shared, software). Clones missing repos, pulls existing clean ones onto main, and skips any repo with uncommitted changes. Use when the user wants to sync/mirror all skillcorner repos locally.
---

# clone-repos

Mirrors every project under the configured GitLab groups to the local machine.
You are just the launcher — all logic (groups, destination, clone/pull/skip
rules) is hardcoded in `workflows/clone_repos.py`.

Behaviour of the workflow:

- **Missing repo** → `git clone` into `<dest>/<group>/<subgroup>/<project>`.
- **Existing repo, clean tree** → `git fetch`, checkout `main` (or the repo
  default if there's no `main`), then `git pull --ff-only`.
- **Existing repo, uncommitted changes** → **skipped, never touched**, and listed
  under "SKIPPED" in the final summary.

Groups synced: `skillcorner/{devops, data-engineering, applications, shared,
software}` (subgroups included). Destination: `./workspace` inside the hub —
the workflow never writes outside the hub repo.

## Steps

1. **Ensure a token is available.** The workflow reads `GITLAB_TOKEN` from the
   environment (a PAT with `read_api` + `read_repository`); it is *not* stored in
   the repo. If the user hasn't exported one, ask them to, e.g.:
   ```
   ! export GITLAB_TOKEN=glpat-...
   ```

2. **Run the workflow** (add `--dry-run` first if the user wants a preview, or
   `--dest <path>` to override the clone root):
   ```bash
   uv run workflows/clone_repos.py
   ```

   It streams live progress — `[i/total] processing: <repo> ...` before each
   git operation, then the outcome — so the user can watch which repo is being
   copied.

3. **Report** the summary the script prints — counts for cloned / updated /
   skipped / errors, and especially the list of repos skipped for having local
   changes so the user can deal with them.

## Notes

- The token is passed to git via an ephemeral `http.extraHeader`, so it is never
  written into any repo's `.git/config`.
- `--ff-only` means a diverged local branch fails loudly rather than creating a
  merge commit — it shows up under ERRORS, not silently merged.
- To schedule unattended, register it as a routine via `/schedule` (make sure
  `GITLAB_TOKEN` is available in that environment).
