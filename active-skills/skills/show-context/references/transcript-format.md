# Claude Code transcript format

This documents the **Claude Code backend** of the harness-agnostic `show-context`
skill — the JSONL format the bundled `scripts/show_context.py` reads. Other
harnesses store the same kinds of injection under different shapes (e.g.
OpenCode keeps a context epoch and message parts in a SQLite DB); the skill's
principle applies to each, but the record schemas below are Claude Code's
alone.

Empirically derived from transcripts written by Claude Code 2.1.x. Field sets
vary across versions — treat every field as optional and degrade gracefully
rather than asserting a shape.

## Contents

- [Location and discovery](#location-and-discovery)
- [Record types](#record-types)
- [Attachment types](#attachment-types)
- [Message content blocks](#message-content-blocks)
- [Adding a renderer](#adding-a-renderer)

## Location and discovery

Transcripts live at:

```
~/.claude/projects/<project-slug>/<session-uuid>.jsonl
```

The slug is derived from cwd by replacing path separators and several other
characters with `-`. `/home/user_name/my.app` and `/home/user-name/my-app`
collapse to the same slug, so the mapping is **not reversible**. Never
reconstruct it. Glob instead:

```
~/.claude/projects/**/<session-uuid>.jsonl
```

The session UUID is in `$CLAUDE_CODE_SESSION_ID`. Related environment
variables that are also present inside a session: `$CLAUDECODE=1`,
`$CLAUDE_CODE_ENTRYPOINT`, `$CLAUDE_CODE_BRIDGE_SESSION_ID` (a differently
formatted `session_...` id used for web links — not the transcript filename).

Sibling directories named after a session UUID hold subagent transcripts.

## Record types

One JSON object per line. `type` discriminates.

| `type` | Meaning |
|---|---|
| `user` | A user turn. May be a typed prompt, injected meta content, or tool results. |
| `assistant` | A model turn. |
| `attachment` | Harness-injected context. The subject of this skill. |
| `system` | Harness events: hook results (`subtype` set, plus `hookInfos`, `hookErrors`, `hookAdditionalContext`), compaction boundaries (`durationMs`, `messageCount`). |
| `file-history-snapshot` | Editor file state for undo. Not context. |
| `ai-title`, `mode`, `permission-mode`, `bridge-session`, `last-prompt` | Session metadata. Not context. |

Common envelope fields: `uuid`, `parentUuid`, `timestamp`, `sessionId`, `cwd`,
`gitBranch`, `version`, `userType`, `isSidechain`.

`isSidechain: true` marks subagent records. Exclude them from a main-thread
reading.

### Distinguishing `user` records

| Shape | Meaning |
|---|---|
| `promptSource: "typed"`, `origin: {kind: "human"}`, content is a **string** | What the human actually typed. |
| `isMeta: true`, content is a text block | Injected prompt content — slash-command bodies, skill bodies. |
| content is a list of `tool_result` blocks | Tool output returning to the model. |

## Attachment types

All observed values of `attachment.type`, with their payload fields.

### Memory and instructions

- **`nested_memory`** — `path`, `displayPath`, `content`
  `content` is a nested object: `{path, type, content, contentDiffersFromDisk}`.
  `type` is a scope label such as `"Project"`. `contentDiffersFromDisk: true`
  means the injected copy is stale relative to disk. Covers CLAUDE.md,
  AGENTS.md, and memory files.

### Hooks

- **`hook_success`** — `hookName`, `hookEvent`, `content`, `stdout`, `stderr`,
  `exitCode`, `command`, `durationMs`, `toolUseID`
  `content` is what reached the context window; it is often but not always
  equal to `stdout`. A zero exit with empty `content` means the hook ran and
  injected nothing.
- **`hook_non_blocking_error`** — same minus `content`.
- **`hook_blocking_error`** — `hookName`, `hookEvent`, `blockingError`, `toolUseID`.
- **`hook_system_message`** — `content`, `hookName`, `hookEvent`, `toolUseID`.

### Capability listings

These are **incremental**. The first carries `isInitial: true`; later records
add and remove. Fold them in order to get current state.

- **`skill_listing`** — `content` (the rendered listing), `skillCount`,
  `names`, `isInitial`.
- **`invoked_skills`** — `skills`.
- **`agent_listing_delta`** — `addedTypes`, `addedLines`, `removedTypes`,
  `isInitial`, `showConcurrencyNote`.
- **`deferred_tools_delta`** — `addedNames`, `addedLines`, `removedNames`,
  `readdedNames`, and sometimes `pendingMcpServers`, `needsAuthMcpServers`.
- **`mcp_instructions_delta`** — `addedNames`, `addedBlocks`, `removedNames`.
- **`command_permissions`** — `allowedTools`.

### Files

- **`file`** — `filename`, `content`, `displayPath`.
- **`directory`** — `path`, `content`, `displayPath`.
- **`edited_text_file`** — `filename`, `snippet`.
- **`compact_file_reference`** — `filename`, `displayPath`.
- **`read_truncation_notice`** — `banner`, `toolUseID`.

### Session state

- **`task_reminder`** — `content`, `itemCount`.
- **`output_style`** — `style`.
- **`date_change`** — `newDate`.
- **`queued_command`** — `prompt`, `commandMode`, `origin`, `timestamp`,
  sometimes `source_uuid`.

## Message content blocks

`message.content` is either a string or a list of blocks:

| Block `type` | Fields |
|---|---|
| `text` | `text` |
| `thinking` | `thinking` |
| `tool_use` | `name`, `input`, `id` |
| `tool_result` | `content` (string or list), `tool_use_id`, `is_error` |

## Adding a renderer

`scripts/show_context.py` maps `attachment.type` to a render function in
`RENDERERS` and falls back to a JSON dump for anything unmapped. Unmapped
types are collected into an "Unrecognized attachment types" section rather
than dropped, so a new harness version degrades to a raw dump instead of
silent data loss.

To add support for a type: write a `render_<name>(attachment) -> str`
returning markdown, register it in `RENDERERS`, and add the type to the
appropriate entry in `SECTIONS` so it lands in a named section.
