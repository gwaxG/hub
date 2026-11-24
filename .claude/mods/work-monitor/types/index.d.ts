export type MergeRequestRow = {
  ref: string
  title: string
  url: string
  isDraft: boolean
  isReview: boolean
  approvedBy: string[]
  package: string
  pipeline: { status: string; url: string } | null
}

export type UsageRow = { name: string; hour: number; window: number }

/** Weighted tokens of the last hour and of the last 5 hours: the sessions that used most, and the others as one row. */
export type Usage = {
  hour: number
  window: number
  biggest: UsageRow[]
  others: UsageRow | null
}

export type Snapshot = {
  usage: Usage | null
  mergeRequests: MergeRequestRow[]
  errors: string[]
  refreshedAt: number
}

declare module 'claude-code' {
  interface PluginState {
    'work-monitor': { snapshot: Shaped<Snapshot> }
  }
}
