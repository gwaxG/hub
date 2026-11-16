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
const DAY = 24 * 3600_000
const entry = (name: string, kind: 'file' | 'dir') => ({ name, kind, size: 1, mtimeMs: Date.now(), isLink: false })
const stored = (n: number, title: string, ago: number) => ({
  sessionId: `local_${n}`,
  cliSessionId: `cli-${n}`,
  cwd: '/work/repo',
  title,
  isArchived: false,
  lastActivityAt: Date.now() - ago,
  latestUserFrameAt: Date.now() - ago,
  postTurnSummary: n === 1 ? { status_category: 'blocked', status_detail: 'MR ready', needs_action: 'Approve the deploy' } : null,
})
const RECORDS: Record<string, object> = {
  'local_1.json': stored(1, 'Fix race', 0),
  'local_2.json': stored(2, 'Big refactor', 3 * DAY),
  'local_3.json': stored(3, 'Small question', 3 * DAY),
}
// Fresh tokens per transcript, and the MR session 1 produced.
const TOKENS: Record<string, number> = { 'cli-1': 5000, 'cli-2': 150_000, 'cli-3': 10_000 }
const MR_1 = 'https://gitlab.com/g/repo/-/merge_requests/1'
const scanOf = (path: string) => {
  const id = path.split('/').pop()!.slice(0, -6)
  return { tokens: TOKENS[id], mentions: id === 'cli-1' ? { [MR_1]: 9 } : { [MR_1]: 2 } }
}
const opened: string[] = []
const LIST = [{ sessionId: 'local_1', isRunning: true }]

const listing = (path: string) =>
  path === ROOT ? [entry('acct', 'dir')] : path.endsWith('acct') ? [entry('org', 'dir')] : Object.keys(RECORDS).map(name => entry(name, 'file'))

const sessionsOnDisk = (on: any) => {
  on('fs.list', (_: unknown, e: { path: string }) => ({ value: listing(e.path) }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }))
  on('fs.read', (_: unknown, e: { path: string }) => ({ value: JSON.stringify(RECORDS[e.path.split('/').pop()!]) }))
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv[0] === 'xdg-open') opened.push(e.argv[1]!)
    const paths = e.argv[0] === 'python3' ? e.argv.slice(3) : []
    const stdout = JSON.stringify(Object.fromEntries(paths.map(path => [path, scanOf(path)])))
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
}

const mr = (iid: string, status: string) => ({
  iid,
  title: `Draft: change ${iid}`,
  webUrl: `https://gitlab.com/g/repo/-/merge_requests/${iid}`,
  draft: true,
  project: { fullPath: 'g/repo' },
  headPipeline: { status, path: `/g/repo/-/pipelines/${iid}` },
  approvedBy: { nodes: iid === '3' ? [{ username: 'reviewer' }] : [] },
})

const GITLAB = { data: { currentUser: { authored: { nodes: [mr('1', 'RUNNING'), mr('2', 'FAILED')] }, review: { nodes: [mr('3', 'SUCCESS')] } } } }

test('the pane lists sessions, active CI and merge requests', async ($, on) => {
  on('command.register', () => ({ value: { command: 'work-monitor' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('clock.every', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/me' : 'token' }))
  sessionsOnDisk(on)
  on('mcp.call', () => ({ value: { content: [{ type: 'text', text: JSON.stringify(LIST) }], isError: false } }))
  on('http.fetch', () => ({ value: { status: 200, ok: true, headers: {}, text: JSON.stringify(GITLAB) } }))

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: 'refresh' })

    expect((await ui.find({ type: 'Text', text: /last 24 hours/ }))?.text).toBe('Sessions · last 24 hours · 1 · 1 running')
    expect((await ui.find({ type: 'Text', text: /last 7 days/ }))?.text).toBe('Sessions · last 7 days · over 100k tokens · 1')
    expect(await ui.find({ type: 'Text', text: /^Big refactor$/ })).toBeTruthy()
    expect(await ui.find({ type: 'Text', text: /^Small question$/ })).toBeFalsy()
    expect(await ui.find({ type: 'Text', text: /^150k$/ })).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /CI · 1 active/ }))?.text).toBe('CI · 1 active')
    expect((await ui.find({ type: 'Text', text: /CI · 1 failed/ }))?.text).toBe('CI · 1 failed')
    expect((await ui.find({ type: 'Text', text: /Review requested · 1/ }))?.text).toBe('Review requested · 1')
    expect(await ui.find({ type: 'Text', text: /^change 1$/ })).toBeTruthy()
    expect(await ui.find({ type: 'Text', text: /^repo$/ })).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /^✓$/ }))?.text).toBe('✓')
    await ui.press({ key: 'session-mine-repo!1' })
    expect(opened.at(-1)).toBe('claude://claude.ai/epitaxy/local_1')
    expect(await ui.find({ type: 'Button', key: 'session-mine-repo!2' })).toBeFalsy()
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
  expect((await ui.find({ type: 'Text', text: /last 24 hours/ }))?.text).toBe('Sessions · last 24 hours · 1 · 1 running')
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

  expect((await ui.find({ type: 'Text', text: /last 24 hours/ }))?.text).toBe('Sessions · last 24 hours · 1')
  expect(await ui.find({ type: 'Text', text: /^Sessions: / })).toBeFalsy()
  await ui.unmount()
})
