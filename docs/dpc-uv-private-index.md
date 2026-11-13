---
repo: [data-provider-clients]
verified_at: 2026-11-04
---

# data-provider-clients: private uv index

- `pyproject.toml` declares `[[tool.uv.index]] name = "internal"`, with
  `url = "https://pypi.skillcorner.com/pypi/internal/simple/"` and `authenticate = "always"` (verified on
  main at 1.16.3). A plain `uv lock` or `uv sync` works with no extra env, and a version bump re-locks
  to a one-line diff.
- **Never** export `UV_DEFAULT_INDEX` (the old GitLab group-index trick) in this repo. It rewrites every
  public package's `source` in `uv.lock` from pypi.org to GitLab (about a 200-line diff). To recover,
  run `git checkout uv.lock`, then `env -u UV_DEFAULT_INDEX uv lock`.
- Fresh venv in a new worktree: set `UV_PYTHON=3.13.4`. Otherwise uv picks the free-threaded 3.14t
  interpreter, and `orjson` (pulled in through fitrequest) fails to build. Moving a worktree breaks its
  `.venv`: delete it and run `uv sync` again.
- From a hub session worktree, the Write/Edit hook only accepts paths under that worktree. Put dpc
  worktrees at `<hub-session-worktree>/<slug>-wt/<repo>` (the hub `.gitignore` ignores `*-wt/`).
