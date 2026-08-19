---
name: show-context
description: "Use this skill whenever the user wants to see or verify what is actually in the session's context window — the user-/project-specific parts. Triggers on /show-context, \"what's in your context\", \"show me your context\", \"dump the context\", \"what context do you have loaded\", \"are my memories being injected\", \"did my instruction file load (CLAUDE.md, AGENTS.md, GEMINI.md)\", \"is AGENTS.md in context\", \"what did the startup hooks add\", \"which skills are loaded\", \"what did that hook inject\", \"confirm X is in context\", or any question about whether a memory, instruction file, hook output, skill listing, or MCP block actually reached the model. Make sure to use this skill even when the user asks casually or about only one piece of context (\"did my memory load?\") — the answer must come from the session transcript, never from introspection or guesswork."
metadata:
  category: product-verification
---

# Show Context

Render, in full, the user- and project-specific context the harness injected
into this session.

## Why this skill exists

Asking an agent "what's in your context?" invites it to answer from
introspection — and introspection is unreliable. The agent cannot reliably
distinguish "I was told this" from "I inferred this," and it cannot see the
difference between a memory file that loaded and one that silently did not.

The session transcript is the ground truth. It records every injection the
harness made, as structured data, before it was ever rendered into the prompt.
Read it and report it.

## The one thing that trips everyone up

Harnesses store the *typed* injection records, not the rendered prompt. The
rendered form — tags, wrapping, merged text — is applied at send time and never
persisted. So: reconstruct from the typed records. Never grep for the rendered
form.

In the **Claude Code** backend this looks like: injected context appears in the
prompt wrapped in `<system-reminder>` tags, but grepping a transcript for
`system-reminder` returns zero hits even in a session with dozens of
injections. What the transcript stores instead is `attachment` records with a
typed payload:

```json
{"type":"attachment","attachment":{"type":"nested_memory","path":"/repo/AGENTS.md",
 "content":{"type":"Project","content":"# Agent Instructions...","contentDiffersFromDisk":false}}}
```

Other harnesses store the same idea differently (e.g. OpenCode keeps a context
epoch + message parts in a SQLite DB). The shape differs; the rule does not —
read the typed records the harness kept, not the rendered prompt you remember.

## How to read the transcript

The mechanism depends on the harness — there is no universal transcript
format. Use whichever ground-truth reader the current harness provides, and
apply the same principle with each: read what it actually stored, then report
it verbatim.

| Harness | How to read the session's injected context |
|---|---|
| **Claude Code** | `python3 <skill-dir>/scripts/show_context.py` — the bundled script. It finds the transcript via `$CLAUDE_CODE_SESSION_ID` under `~/.claude/projects/`. |
| **OpenCode** | The native session tools: `session_list`, `session_info <ses_id>`, `session_read <ses_id>`, `session_search "<q>"`. Sessions live in a SQLite DB, not a JSONL the script can parse. |
| **Other / unknown** | Whatever session-transcript mechanism the harness exposes. If it has none, say so plainly rather than introspecting. |

Running the bundled script in a non-Claude-Code harness does not error — it
detects the harness and prints the pointer above, so you are never left to
guess. An explicit `--transcript <path>` overrides detection and reads that
Claude Code JSONL from anywhere.

### Claude Code backend

```bash
python3 <skill-dir>/scripts/show_context.py
```

That is the default and the common case: every injected item, rendered in
full, for the current session.

Show the output to the user as the answer. Do not summarize it away — the
user asked to see the context, so the rendered dump is the deliverable.

Useful flags:

| Flag | Use |
|---|---|
| `--inventory` | Counts per section, nothing dumped. Good for a first look at a long session. |
| `--only nested_memory,hook` | Restrict to sections. Keys are in the inventory table. |
| `--include messages` | Add prompts, replies, and tool results. |
| `--session <uuid>` / `--transcript <path>` | Inspect a different session. |
| `--list-sessions` | All known transcripts, newest first. |
| `--include-sidechains` | Include subagent records (excluded by default). |

When the user asks about one specific thing ("did my memory load?"), still run
the default or `--inventory` first. The inventory table lists every section
including the empty ones, so an absence is visible as an absence rather than
as a section you forgot to check.

## What the transcript cannot tell you

Say this plainly whenever it matters, rather than implying coverage the output
does not have:

- **The system prompt is not in the transcript.** Tool schemas, the base
  instructions, and anything the harness merges into the system block are
  invisible here. This skill covers everything *else*.
- **The in-flight turn may not be flushed yet.** Records are appended as the
  session progresses, so the newest injection can be missing by a beat.

## Report what is there, not what should be

State what the transcript contains. Do not probe the filesystem to guess at
what "should" have loaded, and do not label an empty section as a bug.

An empty `nested_memory` section is a fact: no memory or instruction file was
injected. Report exactly that. Whether it is a misconfiguration, an empty
directory, or intentional is a separate question the user may then ask — and
at that point, investigating is a normal debugging task, not this skill's job.
The value here is a trustworthy reading, and a reading stops being trustworthy
the moment it mixes in inference.

Two fields are worth calling out when present, because they are facts the dump
already contains and a reader may skim past:

- `contentDiffersFromDisk: true` on a memory file — the injected copy is stale
  relative to the file on disk now.
- A hook with a zero exit code but empty `content` — it ran and injected
  nothing.

## Section keys

These are the **Claude Code backend's** section keys (what the bundled script
renders). Other harnesses expose the same kinds of injection under different
names; map by meaning, not by key.

| Key | Covers |
|---|---|
| `nested_memory` | Instruction files (CLAUDE.md, AGENTS.md, GEMINI.md), memory files, with scope and staleness |
| `hook` | Hook output: success, non-blocking error, blocking error, system message |
| `skills` | Skill listing and invoked skills |
| `agents` | Agent listing deltas |
| `tools` | Deferred tool deltas |
| `mcp` | MCP server instruction blocks |
| `permissions` | Allowed-tools grants |
| `files` | `@`-mentioned files, directories, edit snippets, truncation notices |
| `reminders` | Task reminders, output style, date changes |
| `queued` | Queued commands |
| `meta` | Slash-command and skill bodies injected as prompt content |

Full record schemas for the Claude Code backend are in
`references/transcript-format.md` — read it when adding a renderer or when an
unrecognized attachment type shows up.

## Gotchas & Anti-Patterns

The principle-level rows apply in every harness. Rows naming `<system-reminder>`,
`.jsonl`, `$CLAUDE_CODE_SESSION_ID`, `*_delta`, or sidechains are **Claude Code
backend** specifics — the same mistake takes a different shape in another
harness, so apply the principle rather than the literal check.

| Excuse | Reality |
|---|---|
| "I'll just grep the transcript for `<system-reminder>`" | Returns zero hits always. The tags are added at send time and never stored. You would report "nothing injected" for a session full of injections. |
| "I know what's in my context, I'll just describe it" | Introspection cannot separate what you were told from what you inferred, and cannot see a file that silently failed to load. That uncertainty is the whole reason the user asked. Read the transcript. |
| "The newest `.jsonl` in the project dir is this session" | Subagent sidechains and concurrent sessions write newer files. Use `$CLAUDE_CODE_SESSION_ID`; the script already does. |
| "I'll build the project dir name from cwd by swapping `/` for `-`" | The encoding also flattens `_` and `.`, so it is lossy and not reversible. Glob for `**/<session-id>.jsonl` instead. |
| "The first `*_delta` record shows what tools/agents are loaded" | Deltas are incremental — `isInitial` then adds and removes. Reading only the first misstates the current set. Render every delta event. |
| "The transcript shows my whole context" | It omits the system prompt and tool schemas entirely. Scope the claim to what you actually read. |
| "Section is empty, so the skill is broken / memory is misconfigured" | Empty means nothing of that type was injected. That is the finding. Diagnosing the cause is a separate request. |
| "This dump is long, I'll summarize the interesting parts" | The user asked to see the context. Summarizing returns them to trusting your judgment about what mattered — exactly what they were trying to get away from. Print it; use `--only` or `--inventory` if they ask to narrow. |
| "Sidechain records are context too" | They are a subagent's context, not this session's. They are excluded by default for that reason. |
| "I'm not in Claude Code, so this skill doesn't apply" | The principle does — read your harness's ground-truth transcript/epoch. Only the bundled script is Claude-Code-specific; it points you at the native mechanism when run elsewhere. |
