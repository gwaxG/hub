import type { EngineInterface } from 'claude-code'

import type { Usage } from '../types'

// Sums the usage recorded in the transcripts changed during the last 5 hours; each message id counts once.
// Weighted by price: cache reads 0.1, cache writes 1.25, output 5 times an input token.
const SCAN_PY = String.raw`
import json, os, sys, time
from datetime import datetime
root, now = sys.argv[1], time.time()
HOUR, WINDOW, BIGGEST = 3600, 5 * 3600, 10
WEIGHTS = {"input_tokens": 1, "cache_creation_input_tokens": 1.25, "cache_read_input_tokens": 0.1, "output_tokens": 5}
def source(folder):
    if "claude-mem-observer" in folder: return "claude-mem observer"
    return folder.split("-claude-worktrees-")[-1].strip("-")
hour, window, seen = {}, {}, set()
for folder, _, files in os.walk(root):
    name = source(os.path.relpath(folder, root).split(os.sep)[0])
    for file in files:
        path = os.path.join(folder, file)
        if not file.endswith(".jsonl") or os.path.getmtime(path) < now - WINDOW: continue
        with open(path, errors="ignore") as lines:
            for line in lines:
                if '"usage"' not in line: continue
                try: entry = json.loads(line)
                except ValueError: continue
                message = entry.get("message") or {}
                usage, mid, stamp = message.get("usage"), message.get("id"), entry.get("timestamp")
                if not usage or not mid or not stamp or mid in seen: continue
                age = now - datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                if age > WINDOW: continue
                seen.add(mid)
                tokens = sum((usage.get(k) or 0) * w for k, w in WEIGHTS.items())
                window[name] = window.get(name, 0) + tokens
                if age <= HOUR: hour[name] = hour.get(name, 0) + tokens
names = sorted(window, key=window.get, reverse=True)
row = lambda name, group: {"name": name, "hour": round(sum(hour.get(n, 0) for n in group)), "window": round(sum(window[n] for n in group))}
others = names[BIGGEST:]
print(json.dumps({"hour": round(sum(hour.values())), "window": round(sum(window.values())),
                  "biggest": [row(n, [n]) for n in names[:BIGGEST]],
                  "others": row(str(len(others)) + " other sessions", others) if others else None}))
`

/** Tokens used on this machine in the last hour and the last 5 hours, read from the local transcripts. */
export async function fetchUsage($: EngineInterface): Promise<Usage> {
  const projects = `${await $.env.get('HOME')}/.claude/projects`
  const run = await $.process.run(['python3', '-c', SCAN_PY, projects], { timeoutMs: 60_000 })
  if (run.exitCode !== 0) throw new Error(`usage scan failed: ${run.stderr.trim().split('\n').pop()}`)
  return JSON.parse(run.stdout) as Usage
}
