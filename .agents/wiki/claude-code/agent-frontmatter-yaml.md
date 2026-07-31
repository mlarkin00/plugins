---
type: Pitfall
title: An agent whose frontmatter is not valid YAML is skipped silently
description: Claude Code drops a malformed agent definition with no error — it is simply
  absent from the dispatch list. A `description` carrying `<example>` blocks must be a
  block scalar, and only a real YAML parse detects the failure.
tags:
- claude-code
- agents
- silent-failure
- verification
timestamp: '2026-07-31T02:46:00+00:00'
---

Verified against **Claude Code 2.1.220**.

Agent definitions in `~/.claude/agents/` and `<project>/.claude/agents/` are read
at session start. A file whose frontmatter fails to parse is **skipped without a
warning** — no log line, no startup error. The only symptom is that the agent is
missing from the `Agent` tool's type list, which nothing surfaces until a dispatch
fails:

```
Agent type 'glm-code-reviewer' not found. Available agents: claude, Explore, …
```

## The trap: `<example>` blocks force a block scalar

The house style for an agent `description` embeds `<example>` blocks. Written
plainly, that is invalid YAML — continuation lines sit at column 0, so the scalar
terminates and `<example>` is parsed as a new key:

```yaml
description: Use this agent when …  Examples:      # ✘ ScannerError

<example>
Context: …
</example>
model: sonnet
```

It must be a literal block scalar with every continuation line indented:

```yaml
description: |                                     # ✔ parses
  Use this agent when …  Examples:

  <example>
  Context: …
  </example>
model: sonnet
```

Both forms *look* identical in a terminal, and `grep -A` strips the leading
indentation that distinguishes them — which is how the broken form gets copied
from a working file. The official `plugin-dev` agents use `description: |`.

## Structural checks do not catch it

A hand-rolled validator asserting the frontmatter *contains* `name:`, `model:`,
and three `<example>` tags passes the broken file: every one of those strings is
present. The `plugin-dev` validator's own checklist — "frontmatter with `name`,
`description`, `model`, `color`" — has the same blind spot, because it enumerates
required keys rather than parsing.

Parse it. This is the whole check:

```bash
python3 -c "import yaml,sys; d=yaml.safe_load(open(sys.argv[1]).read().split('---',2)[1]); print(d['name'])" agent.md
```

## Scale of the miss

Two agents symlinked into `~/.claude/agents/` (`memory-puller`, `memory-pusher`,
from `agent-memory` 0.3.3) carried the unquoted form and had been absent from
every session's agent list for as long as they existed. Nobody noticed, because
nothing dispatched them — a silently-skipped agent is indistinguishable from one
you simply never called. They were removed on 2026-07-31; they were also stale
links to a version retired by the agents→skills refactor, so neither would have
loaded even with correct YAML. See
[component support](../antigravity/component-support.md) for why this repo ships
no `agents/` at all.

## Registration is session-start only

Fixing the YAML is not enough within a running session: the registry is built at
startup, and `--continue` / `--resume` reuses it. A dispatch after an in-session
fix still fails with the same "not found" error. A genuinely fresh session is
required, and `/agents` — which previously listed the loaded set — was removed in
2.1.220, so **dispatching the agent is the only remaining confirmation that it
registered.**

This is the agent-definition instance of the rule in
[plugin updates](plugin-updates.md): verify by effect, never from a check whose
pass condition is weaker than the thing it claims to prove.

# Citations

[1] [mlarkin00/plugins](https://github.com/mlarkin00/plugins)
