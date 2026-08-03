# TODO

Marketplace-level backlog. Per-plugin backlogs live in `<plugin>/.agents/TODO.md`;
items here either span plugins or live in the workflows.

Everything below was found in the **2026-07-22 post-restructure runtime review**
(`agy` 1.1.5, Claude Code 2.1.217), which exercised both runtimes end to end.
What passed is recorded at the bottom so a re-check knows what not to re-derive.
Durable runtime behaviour learned that day lives in the OKF bundle at
`wiki/` (`@.agents/wiki/index.md`), not here — this file is only open tasks.

## P0 — Address Immediately

(none)

## P1 — Important / Unblocking

(none — the plugin-agents item was resolved 2026-07-23: all eight agents across
`agent-memory`, `memory-bank` and `llm-wiki` became skills and scripts, so no
plugin ships an `agents/` directory. Evidence and the resulting convention are
in `.agents/wiki/antigravity/component-support.md` and the root briefings'
"No plugin here ships an `agents/` directory" rule.)

## P2 — Nice-to-Have

- [ ] **[P2]** Give `skill-usage/scripts/sync-usage.py` a retry path for an already-committed shard. `sync()` returns early when `git status` shows the counts file clean, so a commit that exists locally but was never pushed (killed worker, offline) waits for new usage to accrue before anything retries it — it self-heals, but with delay. Push when the branch is ahead and `only_our_commits` holds, even with nothing new to commit.
- [ ] **[P2]** Extend `check-briefing-twins.py` to the **per-plugin** briefing pairs, or teach it to report which pairs it does not cover. It guards only the root `AGENTS.md`/`CLAUDE.md`, so `memory-bank/AGENTS.md` and `memory-bank/CLAUDE.md` drifted into direct contradiction unnoticed — AGENTS.md described `sidecar_consolidate.py` phase 1 as local Gemini 3.5 Flash curation long after curation moved server-side to memory-minion (fixed 2026-07-23 in `ce734b1`). `llm-wiki` and `memory-bank` both carry such a pair, and `memory-bank` adds a third file (`GEMINI.md`). The twins are deliberately non-identical, so this needs the same normalize-then-diff treatment the root pair gets, not a byte comparison.
