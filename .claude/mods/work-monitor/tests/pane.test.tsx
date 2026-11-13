import { expect, test } from 'claude-code/testing'

const PANE = {
  plugin: 'work-monitor',
  component: 'Pane',
  requestId: 'work-monitor',
  props: {
    title: 'Work monitor',
    isFocused: false,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 40 },
    view: {},
  },
} as const

const ROOT = '/home/me/.config/Claude/claude-code-sessions'
const entry = (name: string, kind: 'file' | 'dir') => ({ name, kind, size: 1, mtimeMs: Date.now(), isLink: false })
const STORED = {
  sessionId: 'local_1',
  title: 'Fix race',
  isArchived: false,
  lastActivityAt: Date.now(),
  postTurnSummary: { status_category: 'blocked', status_detail: 'MR ready', needs_action: 'Approve the deploy' },
}
const LIST = [{ sessionId: 'local_1', isRunning: true }]

const listing = (path: string) =>
  path === ROOT ? [entry('acct', 'dir')] : path.endsWith('acct') ? [entry('org', 'dir')] : [entry('local_1.json', 'file')]

const sessionsOnDisk = (on: any) => {
  on('fs.list', (_: unknown, e: { path: string }) => ({ value: listing(e.path) }))
  on('fs.read', () => ({ value: JSON.stringify(STORED) }))
}

const mr = (iid: string, status: string) => ({
  iid,
  title: `Draft: change ${iid}`,
  webUrl: `https://gitlab.com/g/repo/-/merge_requests/${iid}`,
  draft: true,
  project: { fullPath: 'g/repo' },
  headPipeline: { status, path: `/g/repo/-/pipelines/${iid}` },
})

const GITLAB = { data: { currentUser: { authored: { nodes: [mr('1', 'RUNNING'), mr('2', 'FAILED')] }, review: { nodes: [mr('3', 'SUCCESS')] } } } }

test('the pane lists sessions, active CI and merge requests', async ($, on) => {
  on('command.register', () => ({ value: { command: 'work-monitor' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/me' : 'token' }))
  sessionsOnDisk(on)
  on('mcp.call', () => ({ value: { content: [{ type: 'text', text: JSON.stringify(LIST) }], isError: false } }))
  on('http.fetch', () => ({ value: { status: 200, ok: true, headers: {}, text: JSON.stringify(GITLAB) } }))

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: 'refresh' })

    expect((await ui.find({ type: 'Text', text: /Sessions · 1 running/ }))?.text).toMatch(/^Sessions · 1 running/)
    expect((await ui.find({ type: 'Text', text: /CI · 1 active/ }))?.text).toBe('CI · 1 active')
    expect((await ui.find({ type: 'Text', text: /CI · 1 failed/ }))?.text).toBe('CI · 1 failed')
    expect((await ui.find({ type: 'Text', text: /Review requested · 1/ }))?.text).toBe('Review requested · 1')
    expect(await ui.find({ type: 'Text', text: /^change 1$/ })).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /Approve/ }))?.text).toBe('Approve the deploy')
    await ui.unmount()
  }
})

test('a GitLab failure is shown and sessions still list', async ($, on) => {
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/me' : 'token' }))
  sessionsOnDisk(on)
  on('mcp.call', () => ({ value: { content: [{ type: 'text', text: JSON.stringify(LIST) }], isError: false } }))
  on('http.fetch', () => ({ value: { status: 401, ok: false, headers: {}, text: '' } }))

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'refresh' })

  expect((await ui.find({ type: 'Text', text: /GitLab/ }))?.text).toBe('GitLab: GitLab answered 401')
  expect((await ui.find({ type: 'Text', text: /^Sessions/ }))?.text).toMatch(/^Sessions · 1 running/)
  await ui.unmount()
})

test('sessions still list from disk without the session server', async ($, on) => {
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/me' : 'token' }))
  sessionsOnDisk(on)
  on('mcp.call', () => {
    throw new Error('no connected MCP tool')
  })
  on('http.fetch', () => ({ value: { status: 200, ok: true, headers: {}, text: JSON.stringify(GITLAB) } }))

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'refresh' })

  expect((await ui.find({ type: 'Text', text: /^Sessions/ }))?.text).toMatch(/^Sessions · 0 running · 1 active/)
  expect(await ui.find({ type: 'Text', text: /^Sessions: / })).toBeFalsy()
  await ui.unmount()
})
