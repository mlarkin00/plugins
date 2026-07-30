# TODO

Durable runtime evidence lives in the repo-root OKF bundle (`.agents/wiki/`), not
here — this file is only open tasks. The three cross-runtime hook P0s fixed on
2026-07-22/23 are recorded there: `cross-runtime/hook-output-protocols.md`
(output shapes), `cross-runtime/payload-key-casing.md` (input keys), and
`antigravity/hooks-contract.md` (the agy manifest).

## P0 — Address Immediately

(none)

## P1 — Important / Unblocking

- [ ] **[P1]** **Repoint this plugin from `mslarkin-agents` to `agentic-ops-dev` — AFTER the `local-minions` fleet has moved.** Operator decision 2026-07-30. This plugin and the `local-minions` fleet deliberately share **one** Memory Bank engine (that repo's `minion-memory/minion_memory/core.py:29-30` says its defaults exist to match this plugin's). That fleet is migrating its Agent Platform assets — Memory Bank, Sessions, and the deployed `memory-minion` — to `agentic-ops-dev`, **region stays `us-west1`**, tracked as a P1 in `local-minions/.agents/TODO.md`. **Sequencing is deliberate: the assets move first, this plugin second.** Until both have moved the memory store is split — the fleet writes to the new engine while this plugin still reads the old one — so keep the gap short, and don't read a "missing" memory in that window as data loss.
  - **What to repoint — three places, not one.**
    - `.claude-plugin/plugin.json:16-18` — `config.project` `"845186993936"`, `config.location` `"us-west1"`, `config.reasoning_engine_id` `"2527865193187246080"`. Project becomes `agentic-ops-dev` (**number `756846227114`** — `README.md:114` calls this field the project *number*, so keep that form), location stays `us-west1`, engine id becomes whatever the new "Shared Agent Persistence" engine is.
    - `scripts/nudge_minion.py:21-22` — `DEFAULT_URL` **hardcodes a second, different resource**: project `845186993936` *and* reasoning engine `3903116745023422464`, which is the deployed **memory-minion**, not the store engine above. Easy to miss because it is a URL string rather than config. It has a `MINION_QUERY_URL` env override, so it can be tested before the constant changes.
    - Docs stating the old values: `README.md:30`, `AGENTS.md:12`, `CLAUDE.md:10`, `GEMINI.md:10`.
  - **TRAP: env vars cannot stage this — the manifest wins.** `scripts/config.py:31-33` resolves `config.get("project") or os.environ.get("GCP_PROJECT", "")`, so a populated `plugin.json` value **shadows** the env var. That is the inverse of `local-minions`, where env overrides the default and a cutover can be staged (and rolled back) without editing code. Here the manifest must actually be edited — so make the change on a branch, and know that rollback is a revert rather than an `unset`. `set_reasoning_engine_id()` (`config.py:36`) already writes the manifest back preserving key order, so the bootstrap path may be reusable rather than hand-editing.
  - **Verify** under the same user hash: `list_memories` returns the migrated facts from the new engine, an `add_memory` write lands there, and `nudge_minion.py` reaches the redeployed memory-minion. Only then is the source safe for the operator to delete — they are handling that deletion manually.

## P2 — Nice-to-Have

- [ ] **[P2]** Reconsider the framing of `memories-curate`. Its premise here ("the sidecar runs identical curation at session end") is stale twice over: there is no sidecar — `sidecar_consolidate.py` is a `Stop` hook — and per the plugin CLAUDE.md, curation is no longer done in this plugin at all. It runs server-side on the deployed **memory-minion** agent (`nudge_minion.py` fires a fail-open nudge; the agent's own 6-hour schedule is the guaranteed trigger). So the local `memories-curate` skill is a manual nudge to that agent, not a local curation pass — reword the skill accordingly or drop it.
- [ ] **[P2]** Retry importing 2 failed memory files into GCP Memory Bank — `README.md` and `project_agent_memory_plugin.md` hit HTTP 400 (likely too large); trim and re-add via `python3 ~/.claude/scripts/memory-bank/add_memory.py`.
- [ ] **[P2]** Add a `memories-query` skill wrapping `query_memories.py` for explicit similarity search.
- [ ] **[P2]** Add `--dry-run` flag to `sidecar_consolidate.py` to preview what would be consolidated without writing.
- [ ] **[P2]** Consider a `verify-memory-bank` skill (health-check + auto-repair, analogous to `verify-memory` in agent-memory).
- [ ] **[P2]** Add a `/memories-graduate` skill wrapping `graduate_memories.py` so graduation can be triggered on-demand from a session without shelling out.
- [ ] **[P2]** Validate graduation output once remember has accumulated archive content — run `python3 scripts/graduate_memories.py --dry-run --force` and confirm candidates look correct. *(2026-06-18: dry-run confirmed correct early-exit when only `today-*.md` exists; re-test once `recent.md` accumulates)*
