export type SessionRow = {
  id: string
  title: string
  isRunning: boolean
  status: string | null
  detail: string | null
  needsAction: string | null
  lastActivityAt: string
}

export type MergeRequestRow = {
  ref: string
  title: string
  url: string
  isDraft: boolean
  isReview: boolean
  pipeline: { status: string; url: string } | null
}

export type Snapshot = {
  sessions: SessionRow[]
  mergeRequests: MergeRequestRow[]
  errors: string[]
  refreshedAt: number
}

declare module 'claude-code' {
  interface PluginState {
    'work-monitor': { snapshot: Shaped<Snapshot> }
  }
}
