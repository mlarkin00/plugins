## Project Goal

GCP-backed long-term memory for Claude Code. Fetches global and project-scoped facts from Vertex AI Reasoning Engine Memory Bank at session start; consolidates new facts at session end.

## Project Context

Claude Code plugin in `mlarkin00/plugins` monorepo. Port of `~/agent-skills/plugins/memory-bank` (Gemini CLI).
Python 3 stdlib only · GCP Vertex AI Memory Bank API · ADC auth.

Config: `.claude-plugin/plugin.json` (`config.project/location/reasoning_engine_id` — currently project `756846227114`/`agentic-ops-dev`, `us-west1`, engine `3095916880561438720`); env-var fallback: `GCP_PROJECT`, `GCP_LOCATION`, `GCP_REASONING_ENGINE`. A populated manifest value **shadows** the env var (`config.py:31-33`), so repointing means editing the manifest.

## Operational Commands

```bash
echo '{}' | python3 scripts/load_context.py          # test session-start injection
python3 scripts/list_memories.py                      # list current-scope memories
python3 scripts/add_memory.py "fact" --scope global   # add a memory
python3 scripts/sidecar_consolidate.py --force        # force daily consolidation
python3 -m unittest discover -s tests -v              # run tests (stdlib unittest, no pytest required)
```

## Style & Conventions

- Python 3 stdlib only.
- Single-responsibility scripts; import helpers via `sys.path.insert`.
- All network calls MUST have timeouts + graceful error handling.
- Default scope: ALWAYS `global`.

## Architecture & Constraints

- `load_context.py` → Claude `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ...}}` by default; `--format agy` → `{"injectSteps": [{"ephemeralMessage": ...}]}` (passed only by `agy_load_context.py`). Wrong shape = silent no-op; test both.
- `save_context.py` → Claude Code transcript format: `role: user/assistant`, content as string or list.
- `sidecar_consolidate.py` → ≤once/24h, walks `~/.claude/projects/**/*.jsonl`.
- `config.py` → reads `../.claude-plugin/plugin.json` via `os.path.realpath(__file__)` — MUST be `realpath`, not `abspath`; symlinks break `abspath`.
- Hook commands use `$CLAUDE_PLUGIN_ROOT`.
- Skills resolve the scripts directory at run time: `~/.claude/scripts/memory-bank`, else `~/.gemini/config/plugins/memory-bank/scripts` (Antigravity), else `~/.claude/plugins/cache/*/memory-bank/*/scripts`. Never `$CLAUDE_PLUGIN_ROOT` — hook-only, empty in a model-run command.
