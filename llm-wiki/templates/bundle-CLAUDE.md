# {{BUNDLE_NAME}} — OKF Bundle

This is an OKF v0.1 knowledge bundle managed by the `llm-wiki` Claude Code plugin.

## Domain

<!-- Describe what this bundle covers. Example:
This bundle documents the BigQuery dataset `bigquery-public-data.crypto_bitcoin` — the
public Bitcoin blockchain data ETL'd by the bitcoin-etl project. -->

TODO: describe this bundle's domain.

## Directory structure

```
{{BUNDLE_DIR}}/
├── index.md              # auto-generated root catalog (do not edit by hand)
├── log.md                # chronological change log (use /llm-wiki:log to append)
├── CLAUDE.md             # this file — the "schema" that disciplines authoring
├── datasets/             # one doc per dataset
├── tables/               # one doc per table or shard family
├── references/           # reference docs: metrics/, joins/, dimensions, etc.
│   ├── metrics/          # one doc per aggregate metric (type: Reference, tags: [metric])
│   └── joins/            # one doc per table-pair join (type: Reference, tags: [join])
└── raw/                  # (optional) immutable source files — read-only inputs
```

## Type vocabulary

The `type` field in frontmatter must be one of:

<!-- Edit this list to match your bundle's domain. Examples: -->
- `BigQuery Dataset` — a top-level dataset
- `BigQuery Table` — a table or shard family
- `Reference` — a reusable reference doc (metrics, joins, enums, etc.)

<!-- For a general knowledge wiki, you might use: -->
<!-- - `Article` — a general knowledge concept -->
<!-- - `Q&A` — a filed query answer -->
<!-- - `Open Question` — a known gap to be filled -->

## What belongs here (read this before writing anywhere)

A repo usually has several documentation layers. They are not interchangeable:

| Layer | Answers | Lifecycle |
|---|---|---|
| `CLAUDE.md` / `AGENTS.md` (repo root) | "What rules must I follow on day one?" | Rewritten; kept short |
| `ARCH.md` / design docs | "How does the system work **now**?" | Rewritten as the system changes |
| **this bundle** | "**Why** is it this way? What did we try? What broke?" | **Append-only; grows forever** |
| `.agents/TODO.md` | "What still needs doing?" | Open tasks only |

The split exists because a current-state document structurally cannot absorb an
append-only history without ceasing to be current-state — that is how backlogs
end up 100 KB with most of it closed entries.

**The pairing rule:** when an incident produces a durable rule, the *rule* goes
in the briefing file and the *evidence* goes here, cross-linked. The briefing
file says what to do; the bundle says why, and what it cost to learn. Neither
should restate the other at length.

**Scope test:** a fact belongs here if it cost investigation to establish and is
not derivable from the code in this repo. Anything a future session could learn
by opening a source file does not.

## Authoring conventions

- **Frontmatter**: `type` is required. Always include `title`, `description` (one tight sentence), and `resource` when there is an underlying asset.
- **Descriptions are the product.** The description is what appears in `index.md`, and the index is what a future session reads before deciding whether to open the doc. Make it a **claim, not a topic** — "agy does not expand `@` imports", not "notes on imports".
- **One concept per doc.** If a doc needs two titles, it is two docs.
- **Body order**: prose → `# Schema` (tables) → `# Common query patterns` (tables) → `# Citations`.
- **Evidence over assertion.** State how the fact was established — the command, the measurement, the observed symptom. A claim with no evidence cannot be re-checked later.
- **Date and version-pin anything time-sensitive** ("probed live 2026-07-21 against v1.1.5", not "apparently").
- **Cross-links**: file-relative paths only (e.g. `[users](../tables/users.md)` from `datasets/`). Never `/absolute/paths.md` — they break GitHub rendering.
- **Citations**: cite only URLs you actually fetched or know. Use `[N] [Title](URL)` format.
- **Prefer the thing that will re-bite.** A fix now covered by a test does not need a doc; a fix that depends on a human remembering does.
- **Do not migrate history in bulk.** Move an old backlog entry here when something actually references it. A wiki nobody reads is worse than a backlog nobody prunes.

## Discoverability — do not remove this

The root `index.md` reaches every session through the host repo's briefing
file(s), installed by `okf_discover.py` between `<!-- llm-wiki:discovery … -->`
markers: a `@{{BUNDLE_DIR}}/index.md` import in a standalone `CLAUDE.md`, or the
catalog **inlined** into `AGENTS.md`/`GEMINI.md`, which Antigravity reads but
does not expand imports from. Titles and descriptions travel; bodies stay on
disk. That is what makes the bundle worth keeping — **recognition replaces
recall**, because an agent cannot notice that it is about to re-derive something.

**If that block is deleted, this bundle stops being read.** Re-check it with:

```
python3 <plugin_root>/scripts/okf_discover.py {{BUNDLE_DIR}} --check
```

The inlined form is a copy and drifts — `/llm-wiki:index` refreshes it.

## Ingest instructions

<!-- Describe how to add new sources. Example: -->

To add a new BigQuery dataset:
```
/llm-wiki:ingest <project.dataset>
```

To add web documentation:
```
/llm-wiki:ingest https://...
# or with a seeds file:
/llm-wiki:ingest seeds.txt
```

## Maintenance

```
/llm-wiki:validate   # check §9 conformance
/llm-wiki:index      # regenerate index.md files, and refresh discovery blocks
/llm-wiki:lint       # semantic health check
/llm-wiki:lint --quick  # mechanical stats only (orphans, broken links, citations)
/llm-wiki:visualize  # generate viz.html graph
/llm-wiki:log        # append a dated entry to log.md
```
