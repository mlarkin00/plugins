## Project Goal

GCP-backed long-term memory for Claude Code. At session start, fetch global and project-scoped facts from the Vertex AI Reasoning Engine Memory Bank and inject them into context. At session end, extract and consolidate new facts from the transcript. Provides manual CRUD skills for direct memory management.

## Project Context

Claude Code plugin in the `mlarkin00/plugins` monorepo (remote: `https://github.com/mlarkin00/plugins`). Equivalent of the Gemini CLI `gcp-memory-bank` plugin (`~/agent-skills/plugins/memory-bank`).

Tech stack: Python 3 (stdlib only) · GCP Vertex AI Reasoning Engine Memory Bank API · ADC via `gcloud` · bash hook scripts.
Plugin root: `~/claude/memory-bank/`

GCP config: project `756846227114` (`agentic-ops-dev`), location `us-west1`, reasoning engine `3095916880561438720` (hardcoded in `.claude-plugin/plugin.json`; env-var fallback: `GCP_PROJECT`, `GCP_LOCATION`, `GCP_REASONING_ENGINE` — note the manifest value **shadows** the env var, so a populated field must be edited, not overridden).

## Operational Commands

```bash
# Verify ADC
gcloud auth application-default print-access-token > /dev/null && echo OK

# Test context load (session start)
echo '{}' | python3 scripts/load_context.py

# Test context save (session end) — pipe a minimal transcript
echo '{"transcriptPath":"/tmp/test.jsonl","workspacePaths":["."]}' | python3 scripts/save_context.py

# Run sidecar consolidation manually
python3 scripts/sidecar_consolidate.py --force

# Add a test memory
python3 scripts/add_memory.py "Test fact from bootstrap" --scope global

# List current memories
python3 scripts/list_memories.py

# Run tests (stdlib unittest — no pytest required)
python3 -m unittest discover -s tests -v
```

## Style & Conventions

- Python 3 stdlib only — no third-party dependencies.
- Each script is single-responsibility; import helpers from `config.py` and `resolve_scope.py`.
- All scripts MUST handle auth failure and network errors gracefully — never crash the session.
- Scripts use `sys.path.insert(0, ...)` to resolve sibling modules; do NOT add `__init__.py`.
- Hook scripts called via `$CLAUDE_PLUGIN_ROOT` must work when stdin is a pipe.
- Default memory scope is ALWAYS `global`; only use `project` when the user explicitly requests it.

## Architecture & Constraints

- Two hook manifests, one per runtime, and BOTH must be updated together. `hooks/hooks.json` (Claude): `SessionStart` → `install-symlinks.sh` then `load_context.py`; `Stop` → `save_context.py` then `sidecar_consolidate.py`. Root `hooks.json` (Antigravity): `PreInvocation` → `agy_load_context.py` (there is no `SessionStart`, so it gates on `conversationId` and replays a cached payload); `Stop` → the same two writers. Claude commands use `$CLAUDE_PLUGIN_ROOT`; agy commands MUST be relative (`./scripts/x.py`).
- `load_context.py` emits the **caller's** hook shape and defaults to Claude Code's: `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<long_term_memories>..."}}`, or `{}` when there is nothing to inject. `--format agy` switches it to `{"injectSteps": [{"ephemeralMessage": ...}]}`, and only `agy_load_context.py` passes it. The wrong shape is injected as nothing while the hook still exits 0, so a change here MUST assert both shapes and that the injected field is non-empty — see `.agents/wiki/cross-runtime/hook-output-protocols.md` in the repo root.
- `save_context.py` reads Claude Code transcript format: `{"role": "user"|"assistant", "content": string|[{type,text}]}`.
- `upload_session.py` stores the full opencode session transcript on the Agent Engine **Session Service** — `POST .../sessions?sessionId={id}` (create-or-get, idempotent) then `POST .../sessions/{id}:appendEvent` per turn. Session events are Content-shaped (`author: "user"|"agent"`, `content.role: "user"|"model"` — `assistant` maps to `agent`/`model`). Scope: `userId` = `resolve_user_id()`, `labels.project` = `"global"` (same model as `save_context.py`). Called from `opencode/plugins/memory-bank.ts` on `session.idle`, growth-gated by a per-sessionID message-count Map so only new turns are appended (append-only, no duplicates). Fail-open. See `.agents/wiki/cross-runtime/agent-engine-session-service.md` for the API surface.
- `sidecar_consolidate.py` runs at most once per 24 hours (`--force` bypasses; state in `~/.cache/memory-bank/.sidecar_state.json`). Two phases: (1) bulk consolidation — walks `~/.claude/projects/**/*.jsonl` and sends all turns to `memories:generate`; (2) **graduation** — calls `graduate_memories.py` on an independent weekly rate-limit (`--force-graduate` bypasses). It then fires a fail-open `nudge_minion.py`. Despite the name it is a `Stop` hook, not a sidecar — the agy CLI starts no sidecar manager.
- **Curation is NOT done in this plugin.** Dedup, rewriting and display-name maintenance run server-side on the deployed **memory-minion** agent (GCP Agent Runtime, `agentic-minions` repo); `nudge_minion.py` sends a best-effort, fail-open `:query curate` after client writes, and the agent's own 6-hour schedule is the guaranteed trigger, so a failed nudge never affects the session.
- `memories:generate` events MUST be Content-shaped — `{"content": {"role": "user"|"model", "parts": [{"text": …}]}}`. A bare `{"role": "USER", "content": …}` is rejected with HTTP 400; `test_save_context.py` locks the shape.
- `config.py` reads `.claude-plugin/plugin.json` first, falls back to env vars. MUST use `os.path.realpath(__file__)` (not `abspath`) — symlinks via `~/.claude/scripts/memory-bank/` will return empty config if `abspath` is used.
- Skills MUST resolve the scripts directory at run time rather than hardcoding one — the plugin lives somewhere different per runtime. The candidates, in precedence order, are `~/.claude/scripts/memory-bank` (the version-free symlink `install-symlinks.sh` maintains on Claude Code), `~/.gemini/config/plugins/memory-bank/scripts` (Antigravity), then `~/.claude/plugins/cache/*/memory-bank/*/scripts` as a last resort. Three constraints make that shape non-negotiable: `$CLAUDE_PLUGIN_ROOT` is populated for hooks only and is **empty** in a command the model runs; `ls a b c | head -1` does not honour argument order because `ls` sorts, which silently selects a stale cached copy; and a one-liner using `$(…)` is auto-denied in a headless Antigravity session, so the lookup and the call must be two plain commands.
- Plugin MUST be registered in root `marketplace.json` before release.
- NEVER hardcode user-specific paths; use `os.path.expanduser('~')` or `$HOME`.
