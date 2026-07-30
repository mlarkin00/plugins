# TODO

Durable runtime evidence lives in the repo-root OKF bundle (`.agents/wiki/`), not
here — this file is only open tasks. The three cross-runtime hook P0s fixed on
2026-07-22/23 are recorded there: `cross-runtime/hook-output-protocols.md`
(output shapes), `cross-runtime/payload-key-casing.md` (input keys), and
`antigravity/hooks-contract.md` (the agy manifest).

## P0 — Address Immediately

(none)

## P1 — Important / Unblocking

- [ ] **[P1]** **Delete the old `mslarkin-agents` Memory Bank resources — operator's manual step.** The plugin repoint to `agentic-ops-dev` landed 2026-07-30 and is verified (below), so the source is now safe to remove: reasoning engine `2527865193187246080` (store, "Shared Agent Persistence") and `3903116745023422464` (deployed `memory-minion`), both in project `845186993936` / `us-west1`. Both still held all 17 memories at cutover — **confirm the `local-minions` fleet is also off them before deleting**, since the two share one engine by design (`minion-memory/minion_memory/core.py:29-30`).
  - *Cutover record (2026-07-30).* New values: project `756846227114` (`agentic-ops-dev`), location `us-west1` (unchanged), store engine `3095916880561438720`, memory-minion engine `4732975345110614016`. Changed in three places — `.claude-plugin/plugin.json` `config`, the `DEFAULT_URL` constant in `scripts/nudge_minion.py` (a *second, different* resource — the minion, not the store; easy to miss because it is a URL string rather than config), and the values quoted in `README.md` / `AGENTS.md`. Verified under the same user hash: 17 memories present in the new engine with identical scope distribution, `list_memories` reads them, an `add_memory` write landed in the new engine and **not** the old, `nudge_minion.py` reached the redeployed minion (reviewed 17, snapshot to `gs://agentic-ops-dev-memory-minion-snapshots/`), and both hook output shapes inject. 37 tests pass.
  - **TRAP worth keeping: env vars cannot stage a cutover here — the manifest wins.** `scripts/config.py:31-33` resolves `config.get("project") or os.environ.get("GCP_PROJECT", "")`, so a populated `plugin.json` value **shadows** the env var. That is the inverse of `local-minions`, where env overrides the default. Here the manifest must actually be edited, and rollback is a revert rather than an `unset`. `nudge_minion.py` is the exception — its `MINION_QUERY_URL` override does work, which is how the new minion was tested before the constant changed.

## P2 — Nice-to-Have

- [ ] **[P2]** Fix the dangling `@`-import in `CLAUDE.md:34` — it cites `@.agents/wiki/cross-runtime/hook-output-protocols.md`, but the bundle is at the **repo root**, so that path does not resolve from `memory-bank/` and the import loads nothing. `AGENTS.md:51` states the same reference correctly (plain path + "in the repo root"). Match that phrasing, or use a working relative path.
- [ ] **[P2]** Reconsider the framing of `memories-curate`. Its premise here ("the sidecar runs identical curation at session end") is stale twice over: there is no sidecar — `sidecar_consolidate.py` is a `Stop` hook — and per the plugin CLAUDE.md, curation is no longer done in this plugin at all. It runs server-side on the deployed **memory-minion** agent (`nudge_minion.py` fires a fail-open nudge; the agent's own 6-hour schedule is the guaranteed trigger). So the local `memories-curate` skill is a manual nudge to that agent, not a local curation pass — reword the skill accordingly or drop it.
- [ ] **[P2]** Retry importing 2 failed memory files into GCP Memory Bank — `README.md` and `project_agent_memory_plugin.md` hit HTTP 400 (likely too large); trim and re-add via `python3 ~/.claude/scripts/memory-bank/add_memory.py`.
- [ ] **[P2]** Add a `memories-query` skill wrapping `query_memories.py` for explicit similarity search.
- [ ] **[P2]** Add `--dry-run` flag to `sidecar_consolidate.py` to preview what would be consolidated without writing.
- [ ] **[P2]** Consider a `verify-memory-bank` skill (health-check + auto-repair, analogous to `verify-memory` in agent-memory).
- [ ] **[P2]** Add a `/memories-graduate` skill wrapping `graduate_memories.py` so graduation can be triggered on-demand from a session without shelling out.
- [ ] **[P2]** Validate graduation output once remember has accumulated archive content — run `python3 scripts/graduate_memories.py --dry-run --force` and confirm candidates look correct. *(2026-06-18: dry-run confirmed correct early-exit when only `today-*.md` exists; re-test once `recent.md` accumulates)*
