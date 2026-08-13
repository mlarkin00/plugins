# Knowledge Bundle (`.agents/wiki/`)

The project's store for **runtime evidence**: facts that cost investigation to
establish and are not derivable from the code. An OKF v0.1 bundle — a directory of
markdown files with YAML frontmatter, one concept per fact.

`AGENTS.md` carries the *rules*. The bundle carries the *evidence* behind them: how
each was established, against which version, and the symptom that exposed it.

## Dependency on `llm-wiki` (decided — do not re-litigate per session)

**Always scaffold the bundle.** The format is plain markdown with YAML frontmatter;
harness-loaded discovery and the one-concept-per-fact discipline are the entire
value, and neither needs tooling. The `llm-wiki` plugin makes the bundle
*maintainable at scale* — `discover`, `index`, `validate`, `lint`, `stats` — but its
absence is not a reason to fall back to a flat file.

- **`llm-wiki` installed** → use `/llm-wiki:init` to scaffold (it installs discovery
  too), and the slash commands below for lifecycle.
- **Not installed** → hand-write `index.md`, `CLAUDE.md`, the concept docs, and the
  discovery blocks to the same shape. Maintain `index.md` by hand (it is small: one
  bullet per concept). Note in the bundle's `CLAUDE.md` that the index and any
  inlined catalog are hand-maintained — nothing refreshes them, so a stale inlined
  copy is the failure to watch for.

`.agents/INSIGHTS.md` is **superseded**. When one exists, migrate its entries into
concepts (one per fact, applying the scope test — most flat-file entries fail it),
then delete the file. Do not maintain both.

## The scope test

A fact belongs in the bundle only if it **cost investigation to establish and is not
derivable from the code**.

| Content | Home |
| :--- | :--- |
| Rules, conventions, commands | `AGENTS.md` |
| Open work | `.agents/TODO.md` |
| System design as shipped | `ARCH.md` |
| Why a rule exists / what broke without it | `.agents/wiki/` |

Without this test the bundle silently becomes a second, worse README.

## Discoverability — harness-loaded content, and it is per-file

The principle is fixed: discovery must be **content the harness loads**, not prose
the agent decides to act on. A prose pointer ("read `.agents/wiki/index.md` before
re-deriving history") was observed sitting in context for a full session without
ever being opened — "I am about to re-derive history" is not a state an agent
recognises about itself.

**The mechanism is not the same in every briefing file.** Measured 2026-07-22
against Claude Code 2.1.218 and `agy` 1.1.5 with a codeword fixture (recorded in
`llm-wiki`'s `scripts/okf_discover.py`):

| Runtime | `CLAUDE.md` | `AGENTS.md` / `GEMINI.md` | `@path` expanded |
| :--- | :--- | :--- | :--- |
| Claude Code | loaded | **not loaded** | yes |
| `agy` | n/a | loaded | **no** |

So there is no single line that works everywhere, and "`@`-import the root index
from the briefing files" is wrong twice over: in `AGENTS.md` an import is invisible
to Claude Code, which never reads that file, and inert under `agy`, which reads it
but does not follow imports.

- **A standalone `CLAUDE.md`** gets `@<bundle>/index.md` — one line, never stale,
  bodies stay on disk. This is the cheap mode; prefer it where it works.
- **`AGENTS.md` / `GEMINI.md`** — and any `CLAUDE.md` that is the *same file* as one
  of them — get the catalog **inlined**, because `agy` will not follow an import.
  Inlined text is a copy, so it goes stale: refresh it with `/llm-wiki:index`.
- **Never inline into both `AGENTS.md` and `GEMINI.md`.** `agy` discovers both, so
  the catalog would land in context twice every turn. `AGENTS.md` is the
  cross-tool name; prefer it.

**Write the import bare — `` `@path` `` in backticks is inert on both runtimes.**
This is the single most common way a correctly-intentioned import silently fails.

```markdown
<!-- llm-wiki:discovery .agents/wiki START -->

## Knowledge bundle — `.agents/wiki`

Open the concept before re-deriving anything it covers.

@.agents/wiki/index.md

<!-- llm-wiki:discovery .agents/wiki END -->
```

With `llm-wiki` installed this is installed and refreshed for you — `/llm-wiki:init`
runs `scripts/okf_discover.py`, which picks the mode per file, and `/llm-wiki:index`
re-syncs the inlined copies. `okf_discover.py <bundle> --check` exits non-zero when
discovery is missing or stale, which is the check to run rather than a bare `grep`
for `@.agents/wiki/index.md`. Without the plugin, write the blocks by hand to the
shape above, keeping the HTML markers so a later `--sync` can find them.

**A bundle whose discovery does not fire is drift; report and fix it.** But judge
that per file and per runtime — a correctly wired `AGENTS.md`-only repo has no
`@`-import anywhere, and grepping for one would report it broken.

**A repo with no `CLAUDE.md` cannot reach a Claude Code session at all**, however
well `AGENTS.md` is wired, because Claude Code never opens that file.
`okf_discover.py` warns about exactly this. The fix is a standalone `CLAUDE.md` —
**not** a symlink to `AGENTS.md`: symlinked briefing files are banned, and
`okf_discover.py` demotes a shared `CLAUDE.md` to inline mode, so the two runtimes
stop getting one copy each. Verified on this repo 2026-08-06, which had `AGENTS.md`
only.

Import mode also costs *less* context than a flat file: the index lists titles and
descriptions only. Measured on `mlarkin00/plugins` — 823 bytes for 12 concepts,
against the 4,369-byte `INSIGHTS.md` it replaced, which loaded whole every session.
Titles in context, bodies on disk. Inline mode pays that 823 bytes in full every
session, which is the price of `agy` reading the bundle at all — past ~6 KB the
catalog has outgrown a briefing file and wants drill-down subdirectory indexes
instead.

## Layout

```
.agents/wiki/
├── index.md          # auto-generated catalog — okf_version: "0.1" frontmatter
├── CLAUDE.md         # domain, scope test, type vocabulary, authoring conventions
└── <topic>/          # one subdirectory per topic, each with its own index.md
    └── <concept>.md
```

Root `index.md` frontmatter is the bundle-root marker — never remove it:

```yaml
---
okf_version: "0.1"
---
```

## Concept doc shape

```markdown
---
type: Runtime Behaviour        # REQUIRED, non-empty. Others: Pitfall, Convention
title: $CLAUDE_PLUGIN_ROOT does not exist in Antigravity
description: The variable is undefined in agy and empty in any model-run command,
  so it cannot be used to locate plugin files.
tags: [antigravity, hooks, paths]
timestamp: '2026-07-22T21:49:59+00:00'
---

The claim, stated up front, with the evidence that established it — the command,
the measurement, the observed symptom.

## Why it matters

The failure it causes, concretely.

## What to do instead

The rule adopted in response (which also lives in `AGENTS.md`).

# Citations

[1] [Source Title](https://example.com/...)
```

Rules:

- **`type` is the only required key**; always also write `title` and `description`.
  The description is what a future session reads in the index before deciding to
  open the doc — make it a **claim, not a topic**.
- Frontmatter key order: `type, resource, title, description, tags, timestamp`.
- **Version-pin every claim** — name the version it was verified against. Runtime
  facts rot; that is their expected failure mode, not a hypothetical.
- **Evidence over assertion.** A claim with no evidence cannot be re-checked when a
  runtime updates.
- **Cross-links are file-relative** (`[x](../antigravity/x.md)`), never absolute —
  absolute paths break GitHub rendering. Link only to concepts that exist.
- Concept ID = path minus `.md`, relative to bundle root. Segments match
  `[A-Za-z0-9_][A-Za-z0-9_.\-]*`.
- Never hand-edit `index.md` when `llm-wiki` is available — regenerate it.

## Lifecycle

| When | Do |
| :--- | :--- |
| A fact passes the scope test | Mint a concept — do not append to an existing one unless it is the same fact |
| After adding/renaming/deleting a doc | Regenerate the index (`/llm-wiki:index`, or `okf_index.py`) — this also re-syncs any inlined catalog, which is a copy and goes stale otherwise |
| After any edit | `/llm-wiki:validate` — §9 conformance, exit non-zero = violation |
| Periodically, and after a dependency upgrade | `/llm-wiki:lint` — contradictions and stale claims; `/llm-wiki:lint --quick` — mechanical only: orphans, broken links, citation coverage |
| A rule in `AGENTS.md` gains evidence | Link the rule to its concept; keep the rule terse |

Where the bundle lives inside a repo that ships `llm-wiki`, its `PostToolUse`
validator additionally blocks a malformed concept doc at write time.

## Anti-patterns

| Excuse | Reality |
| :--- | :--- |
| "I'll add a pointer sentence to `CLAUDE.md` so the agent knows about the wiki." | Prose pointers were observed not firing. Harness-loaded content is the mechanism; a pointer is not a substitute. |
| "I put `` `@.agents/wiki/index.md` `` in the file, so the bundle is wired up." | A backticked `@path` is inert on **both** runtimes — it renders as code, not an import. Write it bare. This is the most common silent failure. |
| "`AGENTS.md` is the cross-tool file, so the import belongs there." | Claude Code never reads `AGENTS.md`, and `agy` reads it but does not follow imports. An import there fires for nobody. `AGENTS.md` needs the catalog **inlined**. |
| "Discovery is installed, so it's done." | An inlined catalog is a *copy*. Every added, renamed, or deleted concept makes it stale. Re-run `/llm-wiki:index` — or `okf_discover.py <bundle> --check`, which exits non-zero on stale. |
| "This project doesn't have `llm-wiki`, so I'll use `INSIGHTS.md`." | The format is markdown + YAML. Scaffold the bundle; hand-maintain the index. |
| "It's one small fact, I'll append it to an existing concept." | One concept per fact. Merged facts cannot be individually version-pinned or invalidated. |
| "I'll write the doc now and pin the version later." | An unpinned claim is indistinguishable from a stale one the moment the runtime updates. |
| "The index is generated, I'll just add a line by hand." | Hand edits are lost on the next regenerate. Regenerate instead — unless the project has no `llm-wiki`, in which case say so in the bundle's `CLAUDE.md`. |

## Worked reference

`mlarkin00/plugins@b77e3cf` — 12 concepts, 20 cross-links, 0 orphans, 0 broken
links, 12/12 citation coverage, §9 conformant, with `.agents/wiki/CLAUDE.md`
recording the scope test and stating that removing the discovery block stops the
bundle being read.
