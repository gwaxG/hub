import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { MergeRequestRow, SessionRow, Snapshot } from '../types'
import { fetchMergeRequests } from './gitlab'
import { fetchSessionWork } from './sessions'

const PANE = 'work-monitor'
const TITLE = 'Work monitor'
const POLL_MS = 60_000
const DAY_MS = 24 * 3600_000
const TOKEN_FLOOR = 100_000
// A short separation line above each repository's group.
const RULE = '─'.repeat(12)
const ACTIVE_CI = new Set(['CREATED', 'WAITING_FOR_RESOURCE', 'PREPARING', 'PENDING', 'RUNNING'])
const STATUS_COLOR: Record<string, string> = {
  SUCCESS: 'success',
  FAILED: 'error',
  RUNNING: 'warning',
  PENDING: 'warning',
  CANCELED: 'inactive',
  MANUAL: 'suggestion',
}

const EMPTY: Snapshot = { sessions: [], mergeRequests: [], errors: [], refreshedAt: 0 }
const snapshot = atom({ plugin: 'work-monitor', key: 'snapshot' } as const, EMPTY, {
  shape: 'snapshot-4',
})

async function settle<T>(work: Promise<T>, label: string, errors: string[]): Promise<T | null> {
  try {
    return await work
  } catch (error) {
    errors.push(`${label}: ${error instanceof Error ? error.message : String(error)}`)
    return null
  }
}

async function refresh($: EngineInterface): Promise<void> {
  const errors: string[] = []
  const [work, mergeRequests] = await Promise.all([
    settle(fetchSessionWork($), 'Sessions', errors),
    settle(fetchMergeRequests($), 'GitLab', errors),
  ])
  await update($, snapshot, previous => ({
    sessions: work?.sessions ?? previous.sessions,
    mergeRequests: mergeRequests?.map(mr => ({ ...mr, origin: work?.originOf(mr.url) ?? null })) ?? previous.mergeRequests,
    errors,
    refreshedAt: Date.now(),
  }))
}

function age(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60_000))
  if (minutes < 60) return `${minutes}m`
  return minutes < 1440 ? `${Math.round(minutes / 60)}h` : `${Math.round(minutes / 1440)}d`
}

function tokens(count: number): string {
  return count >= 1_000_000 ? `${(count / 1_000_000).toFixed(1)}M` : `${Math.round(count / 1000)}k`
}

/** Merge requests grouped by package (wilson, football, ...), packages in name order. */
function byPackage(mergeRequests: MergeRequestRow[]): [string, MergeRequestRow[]][] {
  const groups = new Map<string, MergeRequestRow[]>()
  for (const mr of mergeRequests) groups.set(mr.package, [...(groups.get(mr.package) ?? []), mr])
  return [...groups].sort(([a], [b]) => a.localeCompare(b))
}

function clock(ms: number): string {
  return ms ? new Date(ms).toTimeString().slice(0, 5) : 'never'
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'work-monitor', description: 'Open the work monitor pane' })
    void $.ui.open({ id: PANE, title: TITLE })
    void refresh($)
    $.clock.every(POLL_MS, () => void refresh($))

    return next(e)
  })

  on('command.run', { command: 'work-monitor' }, async $ => {
    await $.ui.open({ id: PANE, title: TITLE })
    void refresh($)

    return { text: 'Work monitor opened.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button, Link } = $.ui.resolve(e)
    const data = await read($, snapshot)

    const section = (title: string, rows: RenderChildren[], empty: string) => (
      <Box flexDirection="column" marginTop={1}>
        <Text bold>{title}</Text>
        {rows.length ? rows : <Text dimColor>{empty}</Text>}
      </Box>
    )

    const grow = (child: RenderChildren) => (
      <Box flexGrow={1} flexShrink={1} minWidth={0}>
        {child}
      </Box>
    )

    const sessionGlyph = (session: SessionRow) =>
      session.isRunning ? (
        <Text color="success">●</Text>
      ) : session.needsAction || session.status === 'blocked' ? (
        <Text color="warning">◆</Text>
      ) : (
        <Text color="inactive">○</Text>
      )

    const sessionRow = (session: SessionRow) => (
      <Box flexDirection="column">
        <Box flexDirection="row" gap={1}>
          {sessionGlyph(session)}
          {grow(<Text wrap="truncate">{session.title}</Text>)}
          <Text dimColor>{tokens(session.tokens)}</Text>
          <Text dimColor>{age(session.workedAt)}</Text>
        </Box>
        {(session.needsAction || session.detail) && (
          <Box paddingLeft={2}>
            <Text dimColor wrap="truncate">
              {session.needsAction || session.detail}
            </Text>
          </Box>
        )}
      </Box>
    )

    const status = (mr: MergeRequestRow) =>
      mr.pipeline ? (
        <Text color={STATUS_COLOR[mr.pipeline.status] ?? 'inactive'}>
          <Link href={mr.pipeline.url}>{mr.pipeline.status.toLowerCase()}</Link>
        </Text>
      ) : (
        <Text dimColor>no ci</Text>
      )

    // Opens the session through the desktop app's claude:// handler; the pane draws only https links.
    const openSession = (mr: MergeRequestRow, place: string) =>
      mr.origin && (
        <Button
          key={`session-${place}-${mr.package}${mr.ref}`}
          label="Session"
          onPress={() => $.process.run(['xdg-open', mr.origin!.link]).then(() => undefined)}
        />
      )

    // `place` names the section, so an MR shown in two sections keys its button apart.
    const mrRow = (mr: MergeRequestRow, place: string, isGrouped = false) => (
      <Box flexDirection="row" gap={1} paddingLeft={isGrouped ? 2 : 0}>
        {status(mr)}
        <Text>
          <Link href={mr.url}>{isGrouped ? mr.ref : `${mr.package}${mr.ref}`}</Link>
        </Text>
        {mr.approvedBy.length > 0 && <Text color="success">✓</Text>}
        {grow(
          <Text wrap="truncate" dimColor={mr.isDraft}>
            {mr.title}
          </Text>,
        )}
        {openSession(mr, place)}
      </Box>
    )

    const grouped = (mergeRequests: MergeRequestRow[], place: string) =>
      byPackage(mergeRequests).map(([name, rows]) => (
        <Box flexDirection="column">
          <Text dimColor>{RULE}</Text>
          <Text>{name}</Text>
          {rows.map(mr => mrRow(mr, place, true))}
        </Box>
      ))

    const running = data.sessions.filter(session => session.isRunning)
    const isToday = (session: SessionRow) => Date.now() - Date.parse(session.workedAt) < DAY_MS
    const today = data.sessions.filter(isToday)
    const week = data.sessions.filter(session => !isToday(session) && session.tokens > TOKEN_FLOOR)
    const activeCi = data.mergeRequests.filter(mr => mr.pipeline && ACTIVE_CI.has(mr.pipeline.status))
    const failedCi = data.mergeRequests.filter(mr => mr.pipeline?.status === 'FAILED')
    const mine = data.mergeRequests.filter(mr => !mr.isReview)
    const review = data.mergeRequests.filter(mr => mr.isReview)

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" gap={1} alignItems="center">
          <Text dimColor>Updated {clock(data.refreshedAt)}</Text>
          <Button key="refresh" label="Refresh" onPress={() => refresh($)} />
        </Box>
        {data.errors.map(error => (
          <Text color="error">{error}</Text>
        ))}
        {section(`CI · ${activeCi.length} active`, activeCi.map(mr => mrRow(mr, 'ci')), 'No pipeline running.')}
        {failedCi.length > 0 && section(`CI · ${failedCi.length} failed`, failedCi.map(mr => mrRow(mr, 'failed')), '')}
        {section(`My merge requests · ${mine.length}`, grouped(mine, 'mine'), 'None open.')}
        {section(`Review requested · ${review.length}`, grouped(review, 'review'), 'None.')}
        {section(
          `Sessions · last 24 hours · ${today.length}${running.length ? ` · ${running.length} running` : ''}`,
          today.map(sessionRow),
          'No session worked in during the last 24 hours.',
        )}
        {section(
          `Sessions · last 7 days · over ${tokens(TOKEN_FLOOR)} tokens · ${week.length}`,
          week.map(sessionRow),
          'None.',
        )}
      </Box>
    )
  })
}
