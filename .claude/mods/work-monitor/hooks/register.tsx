import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { MergeRequestRow, Snapshot, UsageRow } from '../types'
import { fetchMergeRequests } from './gitlab'
import { findOriginLink } from './origin'
import { fetchUsage } from './usage'

const PANE = 'work-monitor'
const TITLE = 'Work monitor'
const POLL_MS = 60_000
// Weighted tokens that fill the plan's 5-hour window: 1.81M read as 7% on 2026-11-18. One reading, so a rough guide.
const WINDOW_BUDGET = 26_000_000
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

const EMPTY: Snapshot = { usage: null, mergeRequests: [], errors: [], refreshedAt: 0 }
const snapshot = atom({ plugin: 'work-monitor', key: 'snapshot' } as const, EMPTY, {
  shape: 'snapshot-10',
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
  const [usage, mergeRequests] = await Promise.all([
    settle(fetchUsage($), 'Tokens', errors),
    settle(fetchMergeRequests($), 'GitLab', errors),
  ])
  await update($, snapshot, previous => ({
    usage: usage ?? previous.usage,
    mergeRequests: mergeRequests ?? previous.mergeRequests,
    errors,
    refreshedAt: Date.now(),
  }))
}

function tokens(count: number): string {
  return count >= 1_000_000 ? `${(count / 1_000_000).toFixed(1)}M` : `${Math.round(count / 1000)}k`
}

/** Opens the session that produced the MR through the desktop app's claude:// handler; the pane draws only https links. */
async function openOrigin($: EngineInterface, mr: MergeRequestRow): Promise<void> {
  const link = await findOriginLink($, mr.url)
  if (link) await $.process.run(['xdg-open', link])
  else await $.ui.toast(`No session found for ${mr.package}${mr.ref}`)
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

    const status = (mr: MergeRequestRow) =>
      mr.pipeline ? (
        <Text color={STATUS_COLOR[mr.pipeline.status] ?? 'inactive'}>
          <Link href={mr.pipeline.url}>{mr.pipeline.status.toLowerCase()}</Link>
        </Text>
      ) : (
        <Text dimColor>no ci</Text>
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
        {mr.ticketUrl && (
          <Text>
            <Link href={mr.ticketUrl}>Notion</Link>
          </Text>
        )}
        <Button key={`session-${place}-${mr.package}${mr.ref}`} label="Session" onPress={() => openOrigin($, mr)} />
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

    const usageRow = (source: UsageRow) => (
      <Box flexDirection="row" gap={1}>
        {grow(<Text wrap="truncate">{source.name}</Text>)}
        <Text dimColor>{tokens(source.hour)}</Text>
        <Text>{tokens(source.window)}</Text>
      </Box>
    )

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
        {data.usage &&
          section(
            `Tokens · last hour ${tokens(data.usage.hour)} · 5 hours ${tokens(data.usage.window)} · ~${Math.round((data.usage.window / WINDOW_BUDGET) * 100)}%`,
            [...data.usage.biggest, ...(data.usage.others ? [data.usage.others] : [])].map(usageRow),
            'No usage.',
          )}
        {section(`CI · ${activeCi.length} active`, activeCi.map(mr => mrRow(mr, 'ci')), 'No pipeline running.')}
        {failedCi.length > 0 && section(`CI · ${failedCi.length} failed`, failedCi.map(mr => mrRow(mr, 'failed')), '')}
        {section(`My merge requests · ${mine.length}`, grouped(mine, 'mine'), 'None open.')}
        {section(`Review requested · ${review.length}`, grouped(review, 'review'), 'None.')}
      </Box>
    )
  })
}
