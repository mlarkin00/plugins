## Project Goal

GCP-backed long-term memory for Claude Code. Fetches global and project-scoped facts from Vertex AI Reasoning Engine Memory Bank at session start; consolidates new facts at session end.

## Project Context

Claude Code plugin in `mlarkin00/plugins` monorepo. Port of `~/agent-skills/plugins/memory-bank` (Gemini CLI).
Python 3 stdlib only · GCP Vertex AI Memory Bank API · ADC auth.

Config lives in `.claude-plugin/plugin.json` (`config.project/location/reasoning_engine_id` — currently project `756846227114`/`agentic-ops-dev`, `us-west1`, engine `3095916880561438720`); env-var fallback: `GCP_PROJECT`, `GCP_LOCATION`, `GCP_REASONING_ENGINE`. The fallback is a fallback only — a populated manifest value **shadows** the env var (`config.py:31-33`), so repointing means editing the manifest, not exporting a variable.

## Operational Commands

```bash
echo '{}' | python3 scripts/load_context.py          # test session-start injection
python3 scripts/list_memories.py                      # list current-scope memories
python3 scripts/add_memory.py "fact" --scope global   # add a memory
python3 scripts/sidecar_consolidate.py --force        # force daily consolidation
python3 scripts/graduate_memories.py --dry-run        # preview remember→memory graduation (no writes)
python3 scripts/graduate_memories.py --force          # force weekly graduation
python3 scripts/resolve_remember.py                   # list discovered remember directories with content
python3 -m unittest discover -s tests -v              # run tests (stdlib unittest, no pytest required)
```

## Style & Conventions

- Python 3 stdlib only — no pip installs.
- Single-responsibility scripts; import `config.py` + `resolve_scope.py` via `sys.path.insert`.
- All network calls MUST have timeouts and graceful exception handling — hooks must never crash the session.
- Default scope: ALWAYS `global`. Use `project` only on explicit user request.

## Architecture & Constraints

- `load_context.py` emits the **caller's** hook shape and defaults to Claude Code's: `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<long_term_memories>..."}}`, or `{}` when there is nothing to inject. `--format agy` switches it to `{"injectSteps": [{"ephemeralMessage": ...}]}`, and only `agy_load_context.py` passes it. The wrong shape is injected as nothing while the hook still exits 0, so a change here MUST assert both shapes and that the injected field is non-empty — see `@.agents/wiki/cross-runtime/hook-output-protocols.md`.
- `save_context.py` handles Claude Code transcript fields: `role: user/assistant`, content as string or list of `{type, text}` blocks.
- `sidecar_consolidate.py` runs ≤once/24h (`--force` bypasses). Two phases: (1) bulk consolidation — walks `~/.claude/projects/**/*.jsonl` and sends to `memories:generate`; (2) **graduation** — calls `graduate_memories.py` on a weekly rate-limit (`--force-graduate` bypasses independently). It then fires a fail-open `nudge_minion.py`.
- **Curation (dedup / rewrite / display-name maintenance) is no longer done in this plugin.** It runs server-side on the deployed **memory-minion** agent (GCP Agent Runtime; see the `agentic-minions` repo). `nudge_minion.py` sends a best-effort, fail-open `:query curate` to that agent after client writes (session-end save, `/memories-add`, sidecar consolidation/graduation); the agent's own 6-hour schedule is the guaranteed trigger, so nudge failures never affect the session.
- `graduate_memories.py` reads remember's compressed files (`archive.md`, `recent.md`) via `resolve_remember.py`, calls Gemini Flash to classify stable facts (user/feedback/project/reference), and promotes them to both memory-bank (GCP API) and agent-memory (`~/.claude/memory/*.md` + git commit/push). Weekly rate-limit stored in `~/.cache/memory-bank/.graduation_state.json`. `today-*.md` files are intentionally excluded (too fresh).
- `resolve_remember.py` discovers remember directories: checks `.remember/` in cwd (legacy mode) and `~/.remember/*/` (external mode). Only returns dirs with non-empty content files.
- Skills resolve the scripts directory at run time (they must not hardcode one): `~/.claude/scripts/memory-bank` (symlink from `install-symlinks.sh`), else `~/.gemini/config/plugins/memory-bank/scripts` (Antigravity), else `~/.claude/plugins/cache/*/memory-bank/*/scripts`. `$CLAUDE_PLUGIN_ROOT` is hook-only and empty in a model-run command; see `AGENTS.md` for why the lookup is two plain commands rather than one `$(…)` line.
- Two hook manifests, one per runtime, and BOTH must be updated together. `hooks/hooks.json` (Claude): `SessionStart` → `install-symlinks.sh` then `load_context.py`; `Stop` → `save_context.py` then `sidecar_consolidate.py`. Root `hooks.json` (Antigravity): `PreInvocation` → `agy_load_context.py`; `Stop` → the same two writers. Claude commands use `$CLAUDE_PLUGIN_ROOT`; agy commands MUST be relative (`./scripts/x.py`).
- `memories:generate` events MUST be Content-shaped — `{"content": {"role": "user"|"model", "parts": [{"text": …}]}}`. A bare `{"role": "USER", "content": …}` is rejected with HTTP 400; `test_save_context.py` locks the shape.
- `config.py` resolves the plugin manifest at `../.claude-plugin/plugin.json` using `os.path.realpath(__file__)` — MUST stay `realpath`, not `abspath`; `abspath` breaks when scripts are invoked via `~/.claude/scripts/memory-bank/` symlinks.
