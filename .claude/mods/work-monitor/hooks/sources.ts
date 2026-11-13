import type { EngineInterface } from 'claude-code'

import type { MergeRequestRow, SessionRow } from '../types'

const GITLAB = 'https://gitlab.com'
const SESSION_SERVER = 'ccd_session_mgmt'
const SESSIONS_DIR = '.config/Claude/claude-code-sessions'
const RECENT_MS = 60 * 60_000

const MR_QUERY = `
fragment mr on MergeRequest {
  iid title webUrl draft project { fullPath } headPipeline { status path }
}
{ currentUser {
  authored: authoredMergeRequests(state: opened, first: 40, sort: UPDATED_DESC) { nodes { ...mr } }
  review: reviewRequestedMergeRequests(state: opened, first: 40, sort: UPDATED_DESC) { nodes { ...mr } }
} }`

type GitlabMr = {
  iid: string
  title: string
  webUrl: string
  draft: boolean
  project: { fullPath: string }
  headPipeline: { status: string; path: string } | null
}

type StoredSession = {
  sessionId: string
  title: string
  isArchived?: boolean
  lastActivityAt: number
  postTurnSummary?: { status_category?: string; status_detail?: string; needs_action?: string } | null
}

/** Reads the token from the environment, else from its export line in ~/.bashrc (the desktop app does not source it). */
async function gitlabToken($: EngineInterface): Promise<string> {
  const fromEnv = await $.env.get('GITLAB_TOKEN')
  if (fromEnv) return fromEnv
  const bashrc = await $.fs.read(`${await $.env.get('HOME')}/.bashrc`)
  const match = /^export GITLAB_TOKEN=["']?([^"'\s]+)/m.exec(bashrc)
  if (!match?.[1]) throw new Error('GITLAB_TOKEN not set')
  return match[1]
}

function toRow(mr: GitlabMr, isReview: boolean): MergeRequestRow {
  const pipeline = mr.headPipeline
  return {
    ref: `${mr.project.fullPath.split('/').pop()}!${mr.iid}`,
    title: mr.title.replace(/^Draft:\s*/i, ''),
    url: mr.webUrl,
    isDraft: mr.draft,
    isReview,
    pipeline: pipeline && { status: pipeline.status, url: GITLAB + pipeline.path },
  }
}

export async function fetchMergeRequests($: EngineInterface): Promise<MergeRequestRow[]> {
  const response = await $.http.fetch(`${GITLAB}/api/graphql`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${await gitlabToken($)}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: MR_QUERY }),
  })
  if (!response.ok) throw new Error(`GitLab answered ${response.status}`)
  const user = JSON.parse(response.text).data?.currentUser
  if (!user) throw new Error('GitLab returned no user')
  const authored = (user.authored.nodes as GitlabMr[]).map(mr => toRow(mr, false))
  const review = (user.review.nodes as GitlabMr[]).map(mr => toRow(mr, true))
  return [...authored, ...review]
}

/** Desktop session records the app keeps on disk; running state is not among them. */
async function storedSessions($: EngineInterface): Promise<StoredSession[]> {
  const root = `${await $.env.get('HOME')}/${SESSIONS_DIR}`
  const since = Date.now() - RECENT_MS
  const files: string[] = []
  for (const account of await $.fs.list(root))
    for (const org of await $.fs.list(`${root}/${account.name}`))
      for (const file of await $.fs.list(`${root}/${account.name}/${org.name}`))
        if (file.kind === 'file' && file.name.endsWith('.json') && file.mtimeMs > since)
          files.push(`${root}/${account.name}/${org.name}/${file.name}`)
  const records = await Promise.all(files.map(async file => JSON.parse(await $.fs.read(file)) as StoredSession))
  return records.filter(record => !record.isArchived && record.lastActivityAt > since)
}

/** Ids of running sessions, from the app's session server; empty where a session has no such server. */
async function runningIds($: EngineInterface): Promise<Set<string>> {
  try {
    const result = await $.mcp.call(SESSION_SERVER, 'list_sessions', { limit: 50 })
    const block = result.content[0]
    if (result.isError || block?.type !== 'text' || !block.text) return new Set()
    const sessions = JSON.parse(block.text) as { sessionId: string; isRunning: boolean }[]
    return new Set(sessions.filter(session => session.isRunning).map(session => session.sessionId))
  } catch {
    return new Set()
  }
}

export async function fetchSessions($: EngineInterface): Promise<SessionRow[]> {
  const [records, running] = await Promise.all([storedSessions($), runningIds($)])
  return records
    .sort((a, b) => b.lastActivityAt - a.lastActivityAt)
    .map(record => ({
      id: record.sessionId,
      title: record.title,
      isRunning: running.has(record.sessionId),
      status: record.postTurnSummary?.status_category || null,
      detail: record.postTurnSummary?.status_detail || null,
      needsAction: record.postTurnSummary?.needs_action || null,
      lastActivityAt: new Date(record.lastActivityAt).toISOString(),
    }))
}
