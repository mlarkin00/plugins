# llm-wiki

Claude Code plugin for creating and maintaining **Open Knowledge Format (OKF) v0.1** knowledge bundles. Implements the [Karpathy LLM-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) with structured data adapters (BigQuery first).

## What it does

Claude becomes the disciplined author and maintainer of a persistent, interlinked markdown wiki:

- **Init** a bundle with conventions, a per-bundle `CLAUDE.md` that disciplines future authoring, and **discovery** wired into the host repo's briefing files so the bundle is actually read
- **Discover** — the root catalog reaches every session unconditionally: a `@bundle/index.md` import in `CLAUDE.md`, or the catalog inlined into `AGENTS.md`/`GEMINI.md` for Antigravity, which loads those but does not expand imports
- **Ingest** from BigQuery datasets, web pages, or local files
- **Enrich** concept docs with prose, schema summaries, query patterns, and cross-links (`/llm-wiki:ingest --re-enrich`)
- **Validate** OKF §9 conformance on every write (PostToolUse hook)
- **Index** auto-generated `index.md` files, bottom-up
- **Visualize** as a self-contained Cytoscape.js HTML graph
- **Lint** for semantic health (contradictions, orphans, stale claims, missing refs)
- **Query** with cited answers; file answers back into the bundle so explorations compound
- **Log** dated provenance entries

## Commands

| Command | What it does |
|---|---|
| `/llm-wiki:init [dir]` | Scaffold a new bundle |
| `/llm-wiki:ingest <source>` | Supervised ingest from any source |
| `/llm-wiki:ingest --re-enrich [concept…]` | Re-enrich named (or all) concepts from their recorded source |
| `/llm-wiki:validate [dir]` | Full §9 conformance check |
| `/llm-wiki:index [dir]` | Regenerate all `index.md` files and refresh discovery blocks |
| `/llm-wiki:visualize [dir]` | Generate `viz.html` graph |
| `/llm-wiki:lint [dir]` | Semantic health check |
| `/llm-wiki:query <q>` | Cited answer from the bundle |
| `/llm-wiki:lint --quick [dir]` | Mechanical stats only, no semantic audit |
| `/llm-wiki:log <entry>` | Append to `log.md` |

## Install

Add to `marketplace.json`:
```json
{"name": "llm-wiki", "source": "./llm-wiki", "description": "OKF knowledge bundle manager", "version": "0.1.0"}
```

Install deps (only for the features you use):
```bash
pip install pyyaml                          # always required
pip install markdownify                     # web ingest
pip install google-cloud-bigquery           # BigQuery adapter
pip install google-genai                    # optional: LLM index descriptions
```

## Quickstart

```
/llm-wiki:init research/llms

# Ingest a web page
/llm-wiki:ingest https://arxiv.org/abs/2307.09288

# Ingest a BigQuery dataset
/llm-wiki:ingest bigquery-public-data.crypto_bitcoin

# Generate the graph
/llm-wiki:visualize research/llms

# Query the wiki
/llm-wiki:query "What is the grain of the transactions table?"
```

## Architecture

- **Scripts** (deterministic): `okf_doc.py`, `okf_validate.py`, `okf_index.py`, `okf_discover.py`, `okf_visualize.py`, `okf_fetch.py`, `okf_bq.py`, `okf_search.py`, `okf_stats.py`
- **Skills** (judgment): one per user-facing operation — `init`, `ingest`, `query`, `lint`, `validate`, `index`, `log`, `visualize` — plus `authoring-concepts`, the shared routine for writing one conformant doc. Source-specific and deep-detail material lives in each skill's `references/`, loaded only when that path is taken:

  ```
  ingest/references/{bigquery,web,re-enrich}.md
  query/references/finding-sources.md
  lint/references/semantic-audit.md
  authoring-concepts/references/okf-spec.md
  ```

- **Hook**: PostToolUse validates every `.md` write for OKF §9 conformance

There are no agents. The former per-concept enricher, web crawler, linter, and source scout are `authoring-concepts`, `ingest/references/web.md`, `lint/references/semantic-audit.md`, and `query/references/finding-sources.md` — Antigravity installs plugin agents but cannot invoke them, so work that must run on both runtimes is a skill. Parallel fan-out (many concepts at once) is a dispatch choice inside `ingest`: parallel `general-purpose` subagents on Claude Code, sequential on Antigravity.

## Provenance

Scripts vendored from [GoogleCloudPlatform/knowledge-catalog](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) (Apache-2.0). The agent harness (ADK + Gemini) is replaced by Claude natively; `google-adk` is not a dependency.
