---
type: Runtime Behaviour
title: Which plugin components actually work on Antigravity
description: Skills and hooks work; agents install but cannot be invoked; sidecars
  never run at all because the CLI starts no sidecar manager.
tags:
- antigravity
- install
timestamp: '2026-07-22T21:49:59+00:00'
---

Established by live `agy -p` sessions, not by installer output.

| Component | Claude Code | Antigravity |
|---|---|---|
| `skills/` | yes | yes — [support files included](skill-support-files.md) |
| hooks | yes | yes — root `hooks.json` only ([contract](hooks-contract.md)) |
| `commands/` | yes (surfaced as skills) | only on the claude-format [install path](install-paths.md) |
| `agents/` | yes | **no** — installed, counted, unreachable |
| `sidecars/` | n/a | **no** — [manager never starts](sidecar-location.md) |

## Agents are unreachable

All eight plugin agents install into `plugins/<name>/agents/` and are counted
(`agents : 3 processed`), but `agy agents` lists nothing and a session asked
directly answers **"NO PLUGIN SUBAGENTS"**, offering only the built-in `research`
and `self`. They are not converted to skills either.

**Consequence:** anything whose remediation is "run the X agent" cannot happen on
Antigravity. Design so that whatever a plugin must *do* there is a skill or a hook.

The fix is to move the agent's procedure into a skill (for judgement-driven work)
or a script the skill calls (for a fixed sequence), keeping **one** copy so the
two runtimes cannot drift. Confirmed on **agy 1.1.5**: after `agent-memory`'s
three agents became the `bootstrap-memory` and `sync-memory` skills, a bulk
install reported `skills: 5 processed / agents: skipped (not found)`, `agy plugin
list` recorded the plugin's components as `["skills", "hooks"]`, and a live `agy`
session with tools disabled confirmed both new skills were loaded and named. A
skill reaches the session; an agent does not.

If you nonetheless author a Claude-only agent, note that its frontmatter fails
[silently when it is not valid YAML](../claude-code/agent-frontmatter-yaml.md) —
the residue of this refactor was two such agents that had never loaded on either
runtime.

## Sidecars never run

The CLI starts no sidecar manager, so a sidecar is inert wherever it is placed —
inside a plugin or in the documented `<config>/sidecars/` location alike. There
is no background execution available to a plugin on this runtime at all.

**Consequence:** periodic work has to hang off `Stop` or `PreInvocation` and be
gated, which means it happens only while someone is using the tool.

# Citations

[1] [mlarkin00/plugins](https://github.com/mlarkin00/plugins)
