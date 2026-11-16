import type { EngineInterface } from 'claude-code'

/** What one session transcript holds for the monitor: fresh tokens and how often it names each MR. */
export type TranscriptScan = { tokens: number; mentions: Record<string, number> }

const EMPTY: TranscriptScan = { tokens: 0, mentions: {} }

// Transcripts run past the 4 MB `$.fs.read` limit, so Python streams them and prints only the totals.
// Fresh tokens = input + output + cache writes; streaming repeats a message's usage per block, so each id counts once.
const SCAN_PY = String.raw`
import json, re, sys
MR = re.compile(r"https://gitlab\.com/[\w./-]+?/-/merge_requests/\d+")
out = {}
for path in sys.argv[1:]:
    seen, tokens, mentions = set(), 0, {}
    with open(path, errors="ignore") as lines:
        for line in lines:
            for url in MR.findall(line):
                mentions[url] = mentions.get(url, 0) + 1
            if '"usage"' not in line:
                continue
            try:
                message = json.loads(line).get("message") or {}
            except ValueError:
                continue
            usage, mid = message.get("usage"), message.get("id")
            if not usage or not mid or mid in seen:
                continue
            seen.add(mid)
            tokens += sum(usage.get(k) or 0 for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens"))
    out[path] = {"tokens": tokens, "mentions": mentions}
print(json.dumps(out))
`

// Scan per transcript path, kept until the file changes.
const cache = new Map<string, { stamp: string; scan: TranscriptScan }>()

async function stampOf($: EngineInterface, path: string): Promise<string | null> {
  const stat = await $.fs.stat(path).catch(() => null)
  return stat && `${stat.mtimeMs}:${stat.size}`
}

/** Scans transcripts, re-reading only those changed since the last call; a missing one scans empty. */
export async function scanTranscripts($: EngineInterface, paths: string[]): Promise<Map<string, TranscriptScan>> {
  const stamps = new Map(await Promise.all(paths.map(async path => [path, await stampOf($, path)] as const)))
  const stale = paths.filter(path => stamps.get(path) && cache.get(path)?.stamp !== stamps.get(path))
  if (stale.length) {
    const run = await $.process.run(['python3', '-c', SCAN_PY, ...stale], { timeoutMs: 120_000 })
    if (run.exitCode !== 0) throw new Error(`transcript scan failed: ${run.stderr.trim().split('\n').pop()}`)
    const scans = JSON.parse(run.stdout) as Record<string, TranscriptScan>
    for (const path of stale) cache.set(path, { stamp: stamps.get(path)!, scan: scans[path] ?? EMPTY })
  }
  return new Map(paths.map(path => [path, stamps.get(path) ? (cache.get(path)?.scan ?? EMPTY) : EMPTY]))
}
