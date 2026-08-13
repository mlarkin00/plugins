# TODO

Marketplace-level backlog. Per-plugin backlogs live in `<plugin>/.agents/TODO.md`;
items here either span plugins or live in the workflows.

Everything below was found in the **2026-07-22 post-restructure runtime review**
(`agy` 1.1.5, Claude Code 2.1.217), which exercised both runtimes end to end.
What passed is recorded at the bottom so a re-check knows what not to re-derive.
Durable runtime behaviour learned that day lives in the OKF bundle at
`wiki/` (`@.agents/wiki/index.md`), not here — this file is only open tasks.

## P0 — Address Immediately

- [ ] **[P0]** Decide how `consolidate-skills` lands on `main` (session 2026-08-13).
  The branch is committed and pushed to `origin/consolidate-skills`, but **not
  merged** — it consolidates `llm-wiki` from 18 skills to 9, which removes nine
  skill directories and retires two slash commands (`/llm-wiki:enrich` →
  `/llm-wiki:ingest --re-enrich`, `/llm-wiki:stats` → `/llm-wiki:lint --quick`).
  Removing skills and renaming commands is a breaking change by the close-session
  criteria, and merging to `main` immediately cuts llm-wiki 0.1.8 via
  `release.yml`, invalidating every version-keyed cache. Downstream is already
  clear: the only external caller, `managing-agent-instructions`, was repointed in
  `mlarkin00/active-skills@e2275c6` and syncs in on its own. So this is a
  release-timing call, not blocked work — `git merge --no-ff consolidate-skills`
  and push, or open a PR, when 0.1.8 should ship.

## P1 — Important / Unblocking

(none — the plugin-agents item was resolved 2026-07-23: all eight agents across
`agent-memory`, `memory-bank` and `llm-wiki` became skills and scripts, so no
plugin ships an `agents/` directory. Evidence and the resulting convention are
in `.agents/wiki/antigravity/component-support.md` and the root briefings'
"No plugin here ships an `agents/` directory" rule.)

## P2 — Nice-to-Have

- [ ] **[P2]** Decide how much staleness the `active-skills` sync may carry when a run simply never happens. On 2026-08-06 six pushes to `mlarkin00/active-skills` between 18:35 and 19:44 UTC produced **zero** `Notify marketplace` runs, and a push here at 20:05 produced no `release.yml` run. Cause was the GitHub Actions incident that began 15:22 UTC (`impact=critical`, "capacity remains constrained and jobs may still be delayed or fail") — **not** a token or config fault: the notify workflow is `state: active`, the repo is public and enabled, and runs #51/#52 show the degradation arriving as 4–10 minute delays before runs stopped being created at all. Nothing to fix in either repo. What it exposes is real, though: an outage produces **no run record whatsoever**, so "Actions is down" and "nothing triggered" look identical in the run list, the mirror silently stops tracking the source, and nothing raises an alarm. The 06:17 UTC daily poll is the only recovery, bounding staleness at ~24h. Options: raise the poll frequency, or have the poll compare the mirrored skill set against the source tree and fail loudly on drift. Related evidence: `.agents/wiki/testing/rsync-protects-excluded.md`.

- [ ] **[P2]** Give `skill-usage/scripts/sync-usage.py` a retry path for an already-committed shard. `sync()` returns early when `git status` shows the counts file clean, so a commit that exists locally but was never pushed (killed worker, offline) waits for new usage to accrue before anything retries it — it self-heals, but with delay. Push when the branch is ahead and `only_our_commits` holds, even with nothing new to commit.
- [ ] **[P2]** Extend `check-briefing-twins.py` to the **per-plugin** briefing pairs, or teach it to report which pairs it does not cover. It guards only the root `AGENTS.md`/`CLAUDE.md`, so `memory-bank/AGENTS.md` and `memory-bank/CLAUDE.md` drifted into direct contradiction unnoticed — AGENTS.md described `sidecar_consolidate.py` phase 1 as local Gemini 3.5 Flash curation long after curation moved server-side to memory-minion (fixed 2026-07-23 in `ce734b1`). `llm-wiki` and `memory-bank` both carry such a pair, and `memory-bank` adds a third file (`GEMINI.md`). The twins are deliberately non-identical, so this needs the same normalize-then-diff treatment the root pair gets, not a byte comparison.
