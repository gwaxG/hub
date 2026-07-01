// daily-brief — project-agnostic morning digest.
//
// Fans out one reader agent per ENABLED connector, then a synthesis agent
// writes a single self-contained HTML digest to the hub's data/ folder.
//
// This orchestration script has no filesystem access, so it takes everything
// via `args` (parse config/hub.config.yaml in the caller and pass it in):
//
//   Workflow({ scriptPath: ".../daily-brief.workflow.js", args: {
//     projectName: "My Project",
//     date: "2026-07-01",                 // caller supplies (Date.* is blocked in scripts)
//     outFile: "/home/andrei/dev/hub/data/digest-2026-07-01.html",
//     connectors: {
//       sentry: { enabled: true,  org: "my-org", projects: [] },
//       gitlab: { enabled: true,  group: "my-group", staleMrsDays: 3 },
//       notion: { enabled: false, watchPages: [] },
//       slack:  { enabled: false, channels: [] },
//     }
//   }})

export const meta = {
  name: 'daily-brief',
  description: 'Fan out over enabled connectors and write one HTML morning digest',
  phases: [{ title: 'Gather' }, { title: 'Synthesize' }],
}

const cfg = args || {}
const c = cfg.connectors || {}
const date = cfg.date || 'today'
const project = cfg.projectName || 'project'

const FINDINGS = {
  type: 'object',
  properties: {
    source: { type: 'string' },
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          detail: { type: 'string' },
          severity: { type: 'string', enum: ['high', 'medium', 'low', 'info'] },
          url: { type: 'string' },
        },
        required: ['title', 'severity'],
      },
    },
  },
  required: ['source', 'items'],
}

// Build one reader task per enabled connector.
const readers = []
if (c.sentry?.enabled)
  readers.push(() => agent(
    `Using the Sentry connector, report NEW or REGRESSED issues in the last 24h for org "${c.sentry.org}"` +
    (c.sentry.projects?.length ? ` projects ${c.sentry.projects.join(', ')}` : '') +
    `. Rank by severity. Return concise findings.`,
    { label: 'sentry', phase: 'Gather', schema: FINDINGS }))

if (c.gitlab?.enabled)
  readers.push(() => agent(
    `Using the GitLab connector for group "${c.gitlab.group}": report failed pipelines in the last 24h and ` +
    `merge requests with no activity for ${c.gitlab.staleMrsDays ?? 3}+ days. Return concise findings.`,
    { label: 'gitlab', phase: 'Gather', schema: FINDINGS }))

if (c.notion?.enabled)
  readers.push(() => agent(
    `Using the Notion connector, report pages/databases changed in the last 24h` +
    (c.notion.watchPages?.length ? ` among ${c.notion.watchPages.join(', ')}` : '') +
    `. Return concise findings.`,
    { label: 'notion', phase: 'Gather', schema: FINDINGS }))

if (c.slack?.enabled)
  readers.push(() => agent(
    `Using the Slack connector, skim channels ${(c.slack.channels || []).join(', ')} for decisions, ` +
    `blockers, or incidents in the last 24h. Return concise findings.`,
    { label: 'slack', phase: 'Gather', schema: FINDINGS }))

if (readers.length === 0) {
  log('No connectors enabled in config — nothing to brief.')
  return { written: null, note: 'enable connectors in config/hub.config.yaml' }
}

// Barrier: we want ALL findings together before synthesizing the single digest.
const found = (await parallel(readers)).filter(Boolean)

phase('Synthesize')
const outFile = cfg.outFile || `/home/andrei/dev/hub/data/digest-${date}.html`
const result = await agent(
  `You are writing the morning engineering brief for "${project}" (${date}).\n\n` +
  `Findings by source (JSON):\n${JSON.stringify(found, null, 2)}\n\n` +
  `Write a SINGLE self-contained HTML file (inline CSS, no external assets) to ${outFile} using the Write tool. ` +
  `Group by source, sort high-severity first, link items that have a url, and open with a 2-3 line summary of what ` +
  `most needs attention today. Keep it skimmable. After writing, report the path.`,
  { label: 'write-digest', phase: 'Synthesize' })

return { written: outFile, sources: found.map(f => f.source), summary: result }
