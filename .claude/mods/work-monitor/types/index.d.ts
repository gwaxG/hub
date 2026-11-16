export type SessionLink = { title: string; link: string }

export type SessionRow = SessionLink & {
  id: string
  isRunning: boolean
  status: string | null
  detail: string | null
  needsAction: string | null
  workedAt: string
  tokens: number
}

export type MergeRequestRow = {
  ref: string
  title: string
  url: string
  isDraft: boolean
  isReview: boolean
  approvedBy: string[]
  package: string
  origin: SessionLink | null
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
