# memory-bank

Claude Code plugin for GCP-backed long-term memory. At session start, facts are fetched from the Vertex AI Reasoning Engine Memory Bank and injected into context. At session end, the conversation transcript is processed to extract and consolidate new facts.

Port of the `gcp-memory-bank` Gemini CLI plugin (`~/agent-skills/plugins/memory-bank`).

---

## How it works

- **SessionStart hook → `load_context.py`**: Queries the GCP Memory Bank for global facts and project-specific facts (scoped by git remote URL). Injects them as a `<long_term_memories>` block into the Claude Code context via `hookSpecificOutput.additionalContext`. Under Antigravity the same loader runs behind `agy_load_context.py`, which requests that runtime's `injectSteps` shape instead.
- **Stop hook → `save_context.py`**: Reads the session transcript and sends conversation events to the GCP `memories:generate` endpoint for LLM-driven extraction.
- **Stop hook → `sidecar_consolidate.py`**: Daily job — aggregates all `~/.claude/projects/**/*.jsonl` transcripts, re-runs generation, and deduplicates the memory store.

### Memory scopes

| Scope | Used for | Default? |
|---|---|---|
| `global` | User preferences, cross-project rules | ✓ Yes |
| `project` | Workspace-specific context (keyed by git remote URL SHA-256) | Only on request |

---

## Prerequisites

- `gcloud` CLI installed and authenticated with Application Default Credentials:
  ```bash
  gcloud auth application-default login
  ```
- The target GCP project (`756846227114` — `agentic-ops-dev`) must have the Vertex AI API enabled.

---

## Installation

### 1. Add the marketplace

```bash
claude plugin marketplace add mlarkin00/plugins
```

### 2. Install

```bash
claude plugin install memory-bank@mlarkin00-plugins
```

The marketplace qualifier is required — a bare name exits "Plugin not found".
On Antigravity, clone the marketplace repo and `agy plugin install <clone>`.

### 3. Bootstrap

Ask any session to "set up memory bank", which triggers the `bootstrap-memory-bank`
skill: it verifies ADC, creates or confirms the reasoning engine, writes a new
engine ID back to the manifest, and confirms context loads. Or run the script:

```bash
python3 ~/.claude/scripts/memory-bank/bootstrap.py              # setup
python3 ~/.claude/scripts/memory-bank/bootstrap.py --import-cc  # setup + import
```

Either way it is idempotent — safe to re-run.

---

## Plugin structure

```
memory-bank/
├── .claude-plugin/
│   └── plugin.json              manifest + GCP config (project, location, engine ID)
├── hooks/
│   └── hooks.json               Claude Code: SessionStart (load) + Stop (save + consolidate)
├── hooks.json                   Antigravity: PreInvocation (load) + Stop (save + consolidate)
├── scripts/
│   ├── config.py                reads .claude-plugin/plugin.json, env-var fallback
│   ├── resolve_scope.py         user hash (gcloud account) + project hash (git remote)
│   ├── load_context.py          SessionStart: fetch + inject memories
│   ├── save_context.py          Stop: extract facts from CC transcript
│   ├── sidecar_consolidate.py   Stop: daily dedup + bulk consolidation
│   ├── add_memory.py            manual add
│   ├── list_memories.py         manual list
│   ├── query_memories.py        manual similarity search
│   ├── update_memory.py         manual update
│   ├── delete_memory.py         manual delete
│   ├── set_project_scope.py     re-scope global → project
│   ├── bootstrap.py             provisions the engine + writes ID back (idempotent)
│   ├── create_engine.py         one-time engine provisioning
│   ├── import_cc_memories.py    import ~/.claude/memory/*.md into GCP
│   ├── upload_session.py        opencode: upload full transcript to Agent Engine Session Service
│   └── install-symlinks.sh      links the scripts into ~/.claude/scripts/memory-bank/
└── skills/
    ├── memory-bank/             /memory-bank — save a high-priority fact immediately
    ├── bootstrap-memory-bank/   set up or restore the GCP engine on a machine
    ├── memories-add/            /memories-add — add a fact
    ├── memories-curate/         /memories-curate — dedup + rewrite (server-side)
    ├── memories-list/           /memories-list — list memories
    ├── memories-update/         /memories-update — update a fact by ID
    ├── memories-delete/         /memories-delete — delete a fact by ID
    └── memories-set-project-scope/  /memories-set-project-scope — narrow global → project
```

There is no `agents/` directory. It held `bootstrap-memory-bank` until 0.1.24,
now the skill and script above: Antigravity installs plugin agents but cannot
invoke them, so anything a plugin must *do* on both runtimes is a skill or hook.

---

## Configuration

Config is read from `.claude-plugin/plugin.json` (hardcoded defaults) with environment variable fallback:

| Key | plugin.json field | Env var |
|---|---|---|
| GCP project number | `config.project` | `GCP_PROJECT` |
| Region | `config.location` | `GCP_LOCATION` |
| Reasoning engine ID | `config.reasoning_engine_id` | `GCP_REASONING_ENGINE` |

To use a different engine, update `.claude-plugin/plugin.json` or set the env vars.
