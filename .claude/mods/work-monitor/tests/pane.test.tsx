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

const opened: string[] = []
const USAGE = { hour: 1_200_000, window: 5_400_000, biggest: [{ name: 'claude-mem observer', hour: 900_000, window: 4_000_000 }], others: { name: '3 other sessions', hour: 0, window: 250_000 } }
// The usage scan answers USAGE; the origin search finds a session for MR 1 only.
const processes = (on: any) =>
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv[0] === 'xdg-open') opened.push(e.argv[1]!)
    const isFound = e.argv[0] === 'sh' && e.argv[4]!.includes('merge_requests/1(')
    const stdout = e.argv[0] === 'python3' ? JSON.stringify(USAGE) : isFound ? 'local_1\n' : ''
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })

const mr = (iid: string, status: string) => ({
  iid,
  title: `Draft: change ${iid}`,
  description: iid === '1' ? 'Part of [the ticket](https://app.notion.com/p/Some-ticket-3b26552a98c9). More text.' : 'Notion 4226, no link.',
  webUrl: `https://gitlab.com/g/repo/-/merge_requests/${iid}`,
  draft: true,
  project: { fullPath: 'g/repo' },
  headPipeline: { status, path: `/g/repo/-/pipelines/${iid}` },
  approvedBy: { nodes: iid === '3' ? [{ username: 'reviewer' }] : [] },
})

const GITLAB = { data: { currentUser: { authored: { nodes: [mr('1', 'RUNNING'), mr('2', 'FAILED')] }, review: { nodes: [mr('3', 'SUCCESS')] } } } }

test('the pane lists active CI and merge requests', async ($, on) => {
  on('command.register', () => ({ value: { command: 'work-monitor' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('clock.every', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/me' : 'token' }))
  processes(on)
  on('ui.toast', () => ({ value: undefined }))
  on('http.fetch', () => ({ value: { status: 200, ok: true, headers: {}, text: JSON.stringify(GITLAB) } }))

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: 'refresh' })

    expect((await ui.find({ type: 'Text', text: /^Tokens/ }))?.text).toBe('Tokens · last hour 1.2M · 5 hours 5.4M · ~21%')
    expect(await ui.find({ type: 'Text', text: /^claude-mem observer$/ })).toBeTruthy()
    expect(await ui.find({ type: 'Text', text: /^900k$/ })).toBeTruthy()
    expect(await ui.find({ type: 'Text', text: /^3 other sessions$/ })).toBeTruthy()
    expect(await ui.find({ type: 'Text', text: /^250k$/ })).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /CI · 1 active/ }))?.text).toBe('CI · 1 active')
    expect((await ui.find({ type: 'Text', text: /CI · 1 failed/ }))?.text).toBe('CI · 1 failed')
    expect((await ui.find({ type: 'Text', text: /Review requested · 1/ }))?.text).toBe('Review requested · 1')
    expect(await ui.find({ type: 'Text', text: /^change 1$/ })).toBeTruthy()
    expect(await ui.find({ type: 'Text', text: /^repo$/ })).toBeTruthy()
    expect((await ui.find({ type: 'Text', text: /^✓$/ }))?.text).toBe('✓')
    // A Link's text is its href, then its label.
    const tickets = (await ui.findAll({ type: 'Link', text: /Notion$/ })).map(link => link.props.href)
    expect(tickets).toEqual(Array(2).fill('https://app.notion.com/p/Some-ticket-3b26552a98c9'))
    await ui.press({ key: 'session-mine-repo!1' })
    expect(opened.at(-1)).toBe('claude://claude.ai/epitaxy/local_1')
    await ui.press({ key: 'session-mine-repo!2' })
    expect(opened.length).toBe(surface === 'terminal' ? 1 : 2)
    await ui.unmount()
  }
})

test('a GitLab failure is shown and tokens still show', async ($, on) => {
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/me' : 'token' }))
  processes(on)
  on('http.fetch', () => ({ value: { status: 401, ok: false, headers: {}, text: '' } }))

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'refresh' })

  expect((await ui.find({ type: 'Text', text: /GitLab/ }))?.text).toBe('GitLab: GitLab answered 401')
  expect(await ui.find({ type: 'Text', text: /^Tokens · last hour/ })).toBeTruthy()
  await ui.unmount()
})

test('the monitor shows no sessions and calls no MCP tool', async ($, on) => {
  on('env.get', (_, e) => ({ value: e.name === 'HOME' ? '/home/me' : 'token' }))
  processes(on)
  on('mcp.call', () => {
    throw new Error('mcp.call is not allowed')
  })
  on('http.fetch', () => ({ value: { status: 200, ok: true, headers: {}, text: JSON.stringify(GITLAB) } }))

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'refresh' })

  expect(await ui.find({ type: 'Text', text: /Sessions|^Tokens: / })).toBeFalsy()
  expect((await ui.find({ type: 'Text', text: /My merge requests/ }))?.text).toBe('My merge requests · 2')
  await ui.unmount()
})
