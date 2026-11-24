import type { EngineInterface } from 'claude-code'

// Prints the id of the desktop session whose transcript names the MR most; nothing where no session does.
// $1 = MR url as a regex, $2 = transcripts folder, $3 = desktop session records folder.
const FIND_SH = String.raw`
for id in $(grep -rcE --include='*.jsonl' --exclude-dir='*claude-mem-observer*' -e "$1" "$2" \
    | grep -v -e ':0$' -e /subagents/ | sort -t: -k2 -nr | head -5 | sed 's|.*/||; s|\.jsonl:.*||'); do
  record=$(grep -rlF --include='local_*.json' "\"$id\"" "$3" | head -1)
  [ -n "$record" ] && basename "$record" .json && exit 0
done
`

/** The claude:// link of the session that produced the MR, searched only when asked; null where none names it. */
export async function findOriginLink($: EngineInterface, mrUrl: string): Promise<string | null> {
  const home = await $.env.get('HOME')
  const pattern = `${mrUrl.replace(/\./g, '\\.')}([^0-9]|$)`
  const folders = [`${home}/.claude/projects`, `${home}/.config/Claude/claude-code-sessions`]
  const run = await $.process.run(['sh', '-c', FIND_SH, 'find-origin', pattern, ...folders], { timeoutMs: 30_000 })
  const id = run.stdout.trim()
  return id ? `claude://claude.ai/epitaxy/${id}` : null
}
