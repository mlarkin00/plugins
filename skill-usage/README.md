# skill-usage

Counts how often each skill is invoked and commits the totals to a git repository you choose.

Works in both Claude Code and Antigravity, and ships **no skills of its own** — it counts every skill invocation, whichever plugin provided it. That is what removes the need to maintain a list of skill names or scope against a particular bundle.

## Install

**Claude Code:**

```
/plugin marketplace add mlarkin00/plugins
/plugin install skill-usage@mlarkin00-plugins
```

**Antigravity:** clone the marketplace repo once, then bulk-install from it —

```bash
git clone https://github.com/mlarkin00/plugins
agy plugin install ./plugins
```

## Configure

Tracking is **opt-in**. Point `SKILL_USAGE_REPO` at a git work tree:

```json
"env": { "SKILL_USAGE_REPO": "/path/to/a/git/repo" }
```

in `~/.claude/settings.json`, which keeps a machine-specific path out of the plugin. Each machine writes **its own file** under `skill-usage/` in that repo:

```
skill-usage/
├─ laptop-3f9c21.json
└─ workstation-a17b04.json
```

```json
{
  "systematic-debugging": { "count": 12, "last_used_at": "2026-07-21T19:49:08Z" }
}
```

Totals are a read-time sum across the shards:

```bash
python3 scripts/report-usage.py               # ranked totals
python3 scripts/report-usage.py --by-machine  # per-machine breakdown
python3 scripts/report-usage.py --json        # machine-readable
```

A machine provisions its own shard on first use — nothing to set up beyond the variable. Note that `~/.claude/settings.json` only injects it into Claude Code; an Antigravity session started from a plain terminal inherits nothing, so export it from your shell profile too if you use `agy` directly:

```bash
export SKILL_USAGE_REPO="$HOME/your-counts-repo"
```

With the variable unset, counts fall back to `~/.claude/skill-usage.json` and no git command runs. `ACTIVE_SKILLS_USAGE_REPO` is still honoured, so installs predating the split out of `active-skills` keep working, and a `skill-usage.json` left at the repo root from before sharding is still summed into totals.

**Usage counts are personal telemetry.** They record which skills you use and when, so a public destination publishes your working habits — permanently, since git history survives deleting the file. Default to a private repo, and choose a public one only deliberately. The counts also cover skills from *every* installed plugin, not just the repo you point at.

## How it works

The two runtimes dispatch skills differently, so each gets its own thin adapter over a shared core:

| | Claude Code | Antigravity |
|---|---|---|
| A skill use appears as | a `Skill` tool call | a read of `skills/<name>/SKILL.md` — there is no skill-activation tool |
| Detected from | `tool_input.skill` | `toolCall.args` path, falling back to the transcript |
| Flush | `SessionEnd` hook | `Stop` hook, throttled to one commit per 30 min |

`active-skills:gcloud` and `gcloud` share one counter, so the two runtimes agree on a single key per skill.

Counts accumulate during a session and are committed in a batch rather than per invocation. Claude Code gets that batching from `SessionEnd`, which fires once. Antigravity has no session-end event, so the flush hangs off `Stop` — which fires at the end of *every* turn — and `sync-usage.py --min-interval 1800` collapses a session's turns into roughly one commit. The tradeoff is that the last turn of a session may fall inside the window; those counts simply ride along with the next session's first eligible flush.

The flush hands the git work to a detached worker and returns in a few milliseconds. It has to: both runtimes cancel a hook still running when the turn or session ends, and a push is a network round trip that does not fit the budget — Claude Code allows the whole `SessionEnd` batch 1.5s and derives that deadline only from hooks declared in `settings.json`, so the `timeout` this plugin declares does not raise it. The worker starts its own session, because the hook's entire process group is signalled on cancellation. Run `sync-usage.py --foreground` to do the work inline instead.

The commit is scoped with `git commit --only` to this machine's shard, so unrelated staged work is untouched, and the sync skips a repo that is mid-merge or mid-rebase. Writes are atomic, and parallel sessions on one machine serialise through an `flock` held outside the repo.

Every hook exits 0 on every path — malformed input, a missing or non-git repo, a failed push. A tracker that blocks a session is worse than one that misses a count.

### Why counts are sharded per machine

A single shared counts file cannot be made safe across machines, and the failure is quiet and destructive rather than obvious:

1. The second machine to push is **rejected**, and a plain `git push` retry never succeeds. Its branch stays ahead forever and its counts reach nobody.
2. Pulling produces a **content conflict** — counts are absolute values, not deltas, so git has no correct merge and resolving it means discarding one machine's numbers.
3. The conflict markers make the file unparseable. An increment landing on it used to read "empty" and **overwrite the file with a single entry**, destroying every count in it.

Sharding removes the shared write target: no two machines ever write the same path, so there is nothing to conflict on. `load()` is also strict now — a file that exists but will not parse raises instead of being treated as empty, so failure mode 3 cannot recur even by another route.

Sharding alone doesn't finish the job, though: a push is still rejected whenever another machine has pushed since your last fetch. So `sync-usage.py` fetches and rebases onto the upstream, which is guaranteed conflict-free because only this machine writes its shard. It rebases **only** when every unpushed commit touches nothing but that shard — if you have real work sitting unpushed, the sync leaves your branch alone and the counts ride along with your next push.

## Antigravity quirks worth knowing

Each fails silently, and each cost real debugging time to find:

- `PostToolUse` handlers must use the nested `{"matcher", "hooks"}` form. The flat `{"type", "command"}` form installs but never fires. `Stop` handlers are the opposite — a flat list, no `matcher` wrapper.
- Sidecars never run. `agy` documents `<config>/sidecars/<id>/sidecar.json` and ships the whole subsystem in the binary, but the CLI never starts the sidecar manager, so a sidecar is inert wherever it is placed. The flush was a scheduled sidecar until 2026-07-22 and had therefore never executed once.

**Retired claim:** this file previously stated that a `Stop` block anywhere in a plugin's `hooks.json` prevents `PostToolUse` from firing, and gave that as the reason the flush was a sidecar. That is not true on `agy` 1.1.5. With both blocks live under one named hook, a session using a skill increments the counter *and* the `Stop` flush commits — verified end to end.

Verified against `agy` 1.1.5.
