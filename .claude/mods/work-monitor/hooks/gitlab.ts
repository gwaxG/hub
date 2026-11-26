import type { EngineInterface } from 'claude-code'

import type { MergeRequestRow } from '../types'

const GITLAB = 'https://gitlab.com'
// The ticket link an MR description carries; no dot in the path, so a sentence's full stop stays out.
const NOTION_URL = /https:\/\/(?:www\.)?(?:notion\.so|app\.notion\.com)\/[\w\-/?=&%#]+/

const MR_QUERY = `
fragment mr on MergeRequest {
  iid title description webUrl draft project { fullPath } headPipeline { status path } approvedBy { nodes { username } }
}
{ currentUser {
  authored: authoredMergeRequests(state: opened, first: 40, sort: UPDATED_DESC) { nodes { ...mr } }
  review: reviewRequestedMergeRequests(state: opened, first: 40, sort: UPDATED_DESC) { nodes { ...mr } }
} }`

type GitlabMr = {
  iid: string
  title: string
  description: string | null
  webUrl: string
  draft: boolean
  project: { fullPath: string }
  headPipeline: { status: string; path: string } | null
  approvedBy: { nodes: { username: string }[] }
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
    ref: `!${mr.iid}`,
    package: mr.project.fullPath.split('/').pop() ?? mr.project.fullPath,
    title: mr.title.replace(/^Draft:\s*/i, ''),
    url: mr.webUrl,
    ticketUrl: NOTION_URL.exec(mr.description ?? '')?.[0] ?? null,
    isDraft: mr.draft,
    isReview,
    approvedBy: mr.approvedBy.nodes.map(user => user.username),
    pipeline: pipeline && { status: pipeline.status, url: GITLAB + pipeline.path },
  }
}

/** GitLab renames a project pending deletion to `<name>-deletion_scheduled-<id>`; its MRs can no longer change. */
function isLive(mr: GitlabMr): boolean {
  return !mr.project.fullPath.includes('-deletion_scheduled-')
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
  const authored = (user.authored.nodes as GitlabMr[]).filter(isLive).map(mr => toRow(mr, false))
  const review = (user.review.nodes as GitlabMr[]).filter(isLive).map(mr => toRow(mr, true))
  return [...authored, ...review]
}
