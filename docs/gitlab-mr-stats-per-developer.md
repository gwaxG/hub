---
repo: [hub]
mr: []
verified_at: 2026-11-24
---

# GitLab MR stats per developer (group-wide)

How to get merged-MR numbers per author and per reviewer for the whole `skillcorner` group in one pass.
Used for the 2026 annual evaluation; method only, no results here.

## Fetch

One GraphQL query on `https://gitlab.com/api/graphql` (Bearer `GITLAB_TOKEN`, `read_api`), paginated 100 per page:

```graphql
group(fullPath: "skillcorner") {
  mergeRequests(state: merged, mergedAfter: $since, includeSubgroups: true, first: 100, after: $after, sort: MERGED_AT_ASC) {
    pageInfo { hasNextPage endCursor }
    nodes { iid title createdAt mergedAt userNotesCount commitCount
            project { fullPath } author { username name } mergeUser { username }
            diffStatsSummary { additions deletions fileCount }
            approvedBy { nodes { username } } reviewers { nodes { username } } }
  }
}
```

- 12 months = about 16,000 MRs, 161 pages, about 3 minutes. No complexity error with these fields.
- REST list endpoints do not return diff stats or approvers; GraphQL gives both in the list.
- `approvedBy` on every MR gives "approvals given" per person without a second query.

## Traps

- Bots: usernames contain `_bot_` (renovate, update-helm-bot, release bots, the AI review bot that approves MRs). Exclude them as authors and as approvers.
- An author can approve their own MR. Count "second human approval" as approvers minus bots minus the author.
- Raw MR counts are not comparable across teams: infra authors merge hundreds of 1-10 line MRs (iamskcr, argocd-configs). Compare inside a repo set (wilson, football, shared libs) or inside one repo.
- `additions` includes lock files and fixtures (one fixture MR = 321k lines). Cap per-MR additions (for example below 20,000) before summing.
- Lock-only MRs (`update son`, `lock`, `pin`, `bump`) distort medians; filter them by title for size and lead-time medians.
- Lead time = `mergedAt - createdAt`; long values mean the MR waited, not that the work was slow.
- Rework proxy: share of `feat` MRs with 300+ additions followed by the same author's `fix`/`revert` MR in the same repo within 7 days. Compute it for peers too; alone it means nothing (wilson backend median is about 50%).

## Other sources for a yearly review

- Notion All Tasks by assignee: see [notion-tasks-ticket-runbook](notion-tasks-ticket-runbook.md). SQL returns 100 rows per call; use `LIMIT 100 OFFSET n`.
- Slack: `slack_search_public_and_private` with `response_format: concise`; `detailed` on broad keywords returns very large payloads.

## Editing the HR xlsx form

The evaluation template has shapes (`<xdr:sp ` in `xl/drawings/`); an openpyxl save drops them. Edit the sheet XML instead:
append `<si>` entries to `sharedStrings.xml`, point the cell at them (`t="s"`), clone the cell `xf` in `styles.xml` for
`wrapText`, and set `ht` on the rows. Merged answer areas: write the top-left cell only. Check the result with
`soffice --headless --convert-to pdf` on a copy with `fitToWidth="1"`.
