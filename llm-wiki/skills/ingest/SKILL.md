---
name: ingest
description: Use when the user invokes /llm-wiki:ingest or asks to ingest, add, or re-enrich a source in an OKF bundle — a BigQuery dataset, a web page or crawl, or local files. Covers source detection, adapter routing, the supervised ingest loop, per-concept dispatch, and the adapter contract for new sources.
---

# /llm-wiki:ingest — Ingest a Source into the Bundle

The supervised ingest loop: detect source → adapter lists concepts → review plan
→ author each concept ([Per-concept dispatch](#per-concept-dispatch)) → review
diff → suggest index + log.

## Usage

```
/llm-wiki:ingest <source> [--auto]
/llm-wiki:ingest <source1> <source2> ... [--auto]
/llm-wiki:ingest --re-enrich [concept-id…]
```

`--auto`: skip review pauses; author across all sources without stopping; one
review at the end. Use when you trust the source and want unattended batch
processing.

`--re-enrich`: no new source — re-author concepts already in the bundle from
their recorded `resource`. See `references/re-enrich.md`.

## Source detection and adapter routing

| Input pattern | Adapter | Script | Detail |
|---|---|---|---|
| `project.dataset` (exactly one `.`) | BigQuery | `okf_bq.py` | `references/bigquery.md` |
| URL (`http://`, `https://`) | Web crawl | `okf_fetch.py` | `references/web.md` |
| `seeds.txt` / `seeds.example.txt` | Web crawl (file of seed URLs) | `okf_fetch.py` | `references/web.md` |
| Local file or directory | Direct read (no script) | — | — |
| `--re-enrich` | Existing bundle docs | per concept's `resource` | `references/re-enrich.md` |
| Git repo URL | Future adapter | — | — |

Read the adapter's reference file **before** listing concepts — each defines its
own `list_concepts` output and its own rules (the web pass in particular carries
a four-gate reference test and non-negotiable augmentation rules).

## The supervised ingest loop

```
1. Detect source type → pick adapter → read its reference file
2. Adapter lists candidate concepts → present the plan (create/update N docs)
     → owner confirms or adjusts
3. Author THIS source's concepts (see Per-concept dispatch below)
     └ each write goes through okf_doc.py (guarded) → PostToolUse hook re-validates
4. Present a diff summary of touched docs → owner reviews
5. Proceed to the next source only on the owner's go
6. Suggest /llm-wiki:index + /llm-wiki:log  (manual, per the plugin's supervised default)
```

**Always show the plan before writing.** The owner may:
- Trim the concept list (e.g. skip low-priority tables)
- Adjust the concept type vocabulary to match the bundle's `CLAUDE.md`
- Add or remove seed URLs for the web pass

With `--auto`, skip the pauses at steps 2 and 4 and present one consolidated
review at the end. Every other rule still applies.

## Per-concept dispatch

Each concept is authored by following the **`authoring-concepts`** skill — one
conformant doc written through `okf_doc.py`. This is the canonical dispatch
contract; the adapter reference files point here.

**How to run the N concepts depends on the runtime, but the procedure does not:**

- **Claude Code** (or any runtime with dispatchable subagents): fan out — invoke
  a `general-purpose` subagent per concept with the Task tool, each told to
  follow `authoring-concepts` with the inputs below. This is the parallel path
  the retired `okf-concept-enricher` agent used to serve.
- **Antigravity** (no dispatchable subagents — plugin agents install but cannot
  be invoked): author the concepts **sequentially** in the current session,
  following `authoring-concepts` for each.

Either way every concept is written exactly once, so the choice is only about
parallelism, never correctness.

Per-concept inputs to pass:

```
  - bundle_root: path to the bundle
  - concept_id: e.g. "tables/users"
  - raw_metadata: JSON from adapter describe()
  - existing_doc: JSON from okf_doc.py read (null if new)
  - concepts_list: JSON from bundle's index.md (for cross-link targets)

Output: one write via okf_doc.py → validated by PostToolUse hook
```

For large datasets (>~10 concepts), present a progress summary after each batch
of ~5 rather than waiting for all — and sequentially, batch in the same way so
the session stays reviewable.

## The adapter contract

Every source adapter provides three operations:

| Operation | Purpose | Returns |
|---|---|---|
| `list_concepts` | candidate concept IDs + types (+ resource URI, optional hint) | list of concept refs |
| `describe(concept)` | raw structured metadata for one concept | dict of metadata |
| `sample(concept)` *(optional)* | a few example rows when metadata is sparse | list of dicts |

An adapter = one **reference file** under `references/` (routing, judgment,
source-specific rules) + an optional **script** (deterministic metadata pull via
CLI).

**Adding a new source** (PDF folder, OpenAPI spec, Postgres, CSV): write one new
`references/<x>.md` describing source detection and `describe` output, add a row
to the routing table above, and optionally add an `okf_<x>.py` script. The
`authoring-concepts` skill turns raw metadata into conformant prose the same way
regardless of source. No core changes, and no new skill.

## Review before proceeding

After each source is ingested, show:
- N docs created, M docs updated
- List of written concept IDs
- Any augmentation guard refusals (with reason)
- Suggested next steps

The owner reviews before moving to the next source.

## After ingest

Always remind the owner to:
```
/llm-wiki:index    — regenerate index.md files
/llm-wiki:log      — record what was ingested
/llm-wiki:validate — confirm conformance
```
