import type { EngineInterface } from 'claude-code'

import type { SessionLink, SessionRow } from '../types'
import { scanTranscripts, type TranscriptScan } from './transcripts'

const SESSION_SERVER = 'ccd_session_mgmt'
const SESSIONS_DIR = '.config/Claude/claude-code-sessions'
const PROJECTS_DIR = '.claude/projects'
const DAY_MS = 24 * 3600_000
// Sessions this old still count as an MR's origin; the lists show the last week only.
const ORIGIN_WINDOW_MS = 30 * DAY_MS
const LIST_WINDOW_MS = 7 * DAY_MS
// Fewer mentions than this is a session that only read or reviewed the MR.
const ORIGIN_MIN_MENTIONS = 5

type StoredSession = {
  sessionId: string
  cliSessionId?: string
  lastAssistantCliSessionId?: string
  cwd?: string
  originCwd?: string
  title: string
  isArchived?: boolean
  lastActivityAt: number
  latestUserFrameAt?: number
  postTurnSummary?: { status_category?: string; status_detail?: string; needs_action?: string } | null
}

type ScannedSession = { record: StoredSession; scan: TranscriptScan }

/** The sessions the panel lists, and which session each MR came from. */
export type SessionWork = { sessions: SessionRow[]; originOf: (mrUrl: string) => SessionLink | null }

/** When the person last sent the session a message; its last activity where that is not recorded. */
function workedAt(record: StoredSession): number {
  return record.latestUserFrameAt ?? record.lastActivityAt
}

function linkOf(record: StoredSession): SessionLink {
  return { title: record.title, link: `claude://claude.ai/epitaxy/${record.sessionId}` }
}

/** One session record; null where the app is rewriting it. */
async function readRecord($: EngineInterface, file: string): Promise<StoredSession | null> {
  try {
    return JSON.parse(await $.fs.read(file)) as StoredSession
  } catch {
    return null
  }
}

/** Desktop session records the person worked in since `since`. */
async function storedSessions($: EngineInterface, home: string | undefined, since: number): Promise<StoredSession[]> {
  const root = `${home}/${SESSIONS_DIR}`
  const files: string[] = []
  for (const account of await $.fs.list(root))
    for (const org of await $.fs.list(`${root}/${account.name}`))
      for (const file of await $.fs.list(`${root}/${account.name}/${org.name}`))
        if (file.kind === 'file' && file.name.endsWith('.json') && file.mtimeMs > since)
          files.push(`${root}/${account.name}/${org.name}/${file.name}`)
  const records = await Promise.all(files.map(file => readRecord($, file)))
  return records.filter((record): record is StoredSession => !!record && !record.isArchived && workedAt(record) > since)
}

/** A session's transcripts: one per cli session id it ran as, under its project folder. */
function transcriptPaths(record: StoredSession, home: string | undefined): string[] {
  const ids = new Set([record.cliSessionId, record.lastAssistantCliSessionId].filter(Boolean))
  const folders = new Set([record.cwd, record.originCwd].filter(Boolean).map(cwd => cwd!.replace(/[^A-Za-z0-9]/g, '-')))
  return [...ids].flatMap(id => [...folders].map(folder => `${home}/${PROJECTS_DIR}/${folder}/${id}.jsonl`))
}

function combine(scans: TranscriptScan[]): TranscriptScan {
  const mentions: Record<string, number> = {}
  for (const scan of scans) for (const [url, count] of Object.entries(scan.mentions)) mentions[url] = (mentions[url] ?? 0) + count
  return { tokens: scans.reduce((sum, scan) => sum + scan.tokens, 0), mentions }
}

async function scanSessions($: EngineInterface, records: StoredSession[], home: string | undefined): Promise<ScannedSession[]> {
  const paths = new Map(records.map(record => [record, transcriptPaths(record, home)]))
  const scans = await scanTranscripts($, [...new Set([...paths.values()].flat())])
  return records.map(record => ({ record, scan: combine(paths.get(record)!.map(path => scans.get(path)!)) }))
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

function toRow({ record, scan }: ScannedSession, running: Set<string>): SessionRow {
  const summary = record.postTurnSummary
  return {
    ...linkOf(record),
    id: record.sessionId,
    isRunning: running.has(record.sessionId),
    status: summary?.status_category || null,
    detail: summary?.status_detail || null,
    needsAction: summary?.needs_action || null,
    workedAt: new Date(workedAt(record)).toISOString(),
    tokens: scan.tokens,
  }
}

/** The session that names an MR most, at least ORIGIN_MIN_MENTIONS times: the one that produced it. */
function originFinder(scanned: ScannedSession[]): SessionWork['originOf'] {
  return mrUrl => {
    let best: ScannedSession | null = null
    for (const one of scanned)
      if ((one.scan.mentions[mrUrl] ?? 0) > (best?.scan.mentions[mrUrl] ?? ORIGIN_MIN_MENTIONS - 1)) best = one
    return best && linkOf(best.record)
  }
}

export async function fetchSessionWork($: EngineInterface): Promise<SessionWork> {
  const home = await $.env.get('HOME')
  const [records, running] = await Promise.all([storedSessions($, home, Date.now() - ORIGIN_WINDOW_MS), runningIds($)])
  const scanned = await scanSessions($, records, home)
  const listed = scanned.filter(({ record }) => workedAt(record) > Date.now() - LIST_WINDOW_MS)
  return {
    sessions: listed.map(one => toRow(one, running)).sort((a, b) => Date.parse(b.workedAt) - Date.parse(a.workedAt)),
    originOf: originFinder(scanned),
  }
}
