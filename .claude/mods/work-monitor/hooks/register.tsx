import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { MergeRequestRow, SessionRow, Snapshot } from '../types'
import { fetchMergeRequests, fetchSessions } from './sources'

const PANE = 'work-monitor'
const TITLE = 'Work monitor'
const POLL_MS = 60_000
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
  shape: 'snapshot-1',
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
  const [sessions, mergeRequests] = await Promise.all([
    settle(fetchSessions($), 'Sessions', errors),
    settle(fetchMergeRequests($), 'GitLab', errors),
  ])
  await update($, snapshot, previous => ({
    sessions: sessions ?? previous.sessions,
    mergeRequests: mergeRequests ?? previous.mergeRequests,
    errors,
    refreshedAt: Date.now(),
  }))
}

function age(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60_000))
  if (minutes < 60) return `${minutes}m`
  return minutes < 1440 ? `${Math.round(minutes / 60)}h` : `${Math.round(minutes / 1440)}d`
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
          <Text dimColor>{age(session.lastActivityAt)}</Text>
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

    const mrRow = (mr: MergeRequestRow) => (
      <Box flexDirection="row" gap={1}>
        {status(mr)}
        <Text>
          <Link href={mr.url}>{mr.ref}</Link>
        </Text>
        {grow(
          <Text wrap="truncate" dimColor={mr.isDraft}>
            {mr.title}
          </Text>,
        )}
      </Box>
    )

    const running = data.sessions.filter(session => session.isRunning)
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
        {section(`CI · ${activeCi.length} active`, activeCi.map(mrRow), 'No pipeline running.')}
        {failedCi.length > 0 && section(`CI · ${failedCi.length} failed`, failedCi.map(mrRow), '')}
        {section(`My merge requests · ${mine.length}`, mine.map(mrRow), 'None open.')}
        {section(`Review requested · ${review.length}`, review.map(mrRow), 'None.')}
        {section(
          `Sessions · ${running.length} running · ${data.sessions.length} active in the last hour`,
          data.sessions.map(sessionRow),
          'No session active in the last hour.',
        )}
      </Box>
    )
  })
}
