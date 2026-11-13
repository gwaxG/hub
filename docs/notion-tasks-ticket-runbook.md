---
repo: [hub]
mr: []
verified_at: 2026-11-04
---

# Notion "📌 All Tasks" ticket runbook

Creating/updating Andrei's work tickets via the Notion MCP.

- Data source: `collection://2dd6552a-98c9-8008-99e8-000ba8d7c41c` (use as `data_source_id` in create-pages, table name in SQL).
- Properties: Name, Status (Backlog / To Do / In Progress / To review / QA / In Review / Blocked / Done / Cancelled), Assignee, Priority, Start Date, Due Date, Done date, Description, Gitlab MR 🦊, Product Area / Domain (relation), Parent Task (relation).
- Andrei's user id: `2fcd872b-594c-81b6-8990-000251a05a7e` (Assignee array; SQL filter `Assignee LIKE '%<id>%'`).
- **Done-date automation:** setting Status=Done stamps Done date = today, overwriting it. To backdate, set Status first, then set `date:Done date:start` in a second update.
- Slack-sourced tickets: always put the thread permalink in Description and page body. Permalink `p1793001624663489` → `ts=1793001624.663489` for `slack_read_thread`.
- Keep sensitive data (client IPs, emails) out of ticket bodies.
- Notion SQL rate-limits (429, retry after 30s); the session transcript often already has the page URL.
- Set a fitting emoji page icon (`icon`) on every new ticket.
