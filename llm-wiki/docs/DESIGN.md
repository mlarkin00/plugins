# OKF Knowledge Bundle Plugin — Design

| | |
|---|---|
| **Status** | Draft — design approved, pre-implementation |
| **Date** | 2026-06-19 |
| **Owner** | Matt Larkin |
| **Plugin name** | `llm-wiki` — commands `/llm-wiki:*`; OKF-format helpers keep the `okf` prefix (`okf_*.py`, `okf-spec`) |
| **Marketplace** | `mlarkin00-plugins` (sibling of `agent-memory`, `memory-bank`, …) |
| **Targets** | OKF v0.1 ([spec](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)) |

---

## 1. Summary

`llm-wiki` is a Claude Code plugin that turns Claude into a disciplined author and maintainer of **Open Knowledge Format (OKF)** bundles — directories of markdown + YAML-frontmatter documents that humans, agents, and catalog tools can all read. It implements the *general* "LLM wiki" pattern (incrementally build and maintain a persistent, interlinked knowledge base) with structured data sources such as BigQuery available as pluggable **adapters**.

The plugin does the *judgment* work (ingesting sources, crawling the web, cross-linking, linting, querying) natively in Claude via **skills** and **subagents**, and reuses the GCP reference implementation's *mechanics* (visualizer, BigQuery metadata extraction, document model, index synthesis) by **vendoring** them as deterministic **scripts**. A single **hook** enforces OKF §9 conformance on every write.

---

## 2. Background & motivation

Three inputs shaped this design:

1. **The OKF v0.1 spec** — formalizes the knowledge-as-markdown idea: a bundle is a directory tree of UTF-8 markdown files; each concept doc has YAML frontmatter (only `type` is required) plus a markdown body; `index.md` and `log.md` are reserved; cross-links are plain markdown; consumption is deliberately permissive (unknown types, broken links, missing fields must be tolerated). The spec is the interoperability contract.

2. **Karpathy's "LLM wiki" pattern** — describes the *workflow*: an LLM incrementally compiles raw sources into a persistent, compounding wiki and owns the bookkeeping (summarizing, cross-referencing, filing, linting) that causes humans to abandon wikis. Three layers — **raw sources → the wiki → the schema** (a `CLAUDE.md` that disciplines the LLM) — and three operations — **ingest / query / lint**.

3. **The GCP reference implementation** (`knowledge-catalog/okf`) — a Google ADK + Gemini "enrichment agent" that produces OKF bundles from BigQuery (a "BQ pass" writing one doc per table/dataset, then a budgeted "web pass" that crawls seed URLs to enrich docs or mint `references/`), plus a self-contained Cytoscape HTML visualizer that consumes a bundle.

**The synthesis insight.** The reference agent rebuilds an entire agent harness (ADK + Gemini + hand-written tools, a `Source` interface, an index synthesizer) to do work **Claude Code already does natively**: read/write markdown, fetch and follow links with judgment, reason over schemas. So we do **not** re-wrap that agent. We express the judgment work as native Claude skills + subagents, and reuse the reference repo only for the **deterministic mechanics** that must never hallucinate or burn tokens. This needs no ADK and no Gemini for the core loop, and generalizes past BigQuery.

---

## 3. Goals & non-goals

**Goals**

- Author and maintain **OKF v0.1-conformant** bundles end to end: init → ingest → cross-link → index → lint → query → visualize.
- Make Claude the wiki maintainer (Karpathy's three operations) for **general** knowledge: documents, web pages, notes — not just data catalogs.
- Guarantee conformance, stable index files, an enforced crawl budget, and byte-stable doc serialization via **deterministic scripts**, not model output.
- Keep structured sources (BigQuery first) behind a **uniform adapter seam** so new sources are additive.
- Be a well-formed plugin in the `mlarkin00-plugins` marketplace, self-contained (vendored, no fragile external package dependency).

**Non-goals**

- Re-implementing or wrapping the upstream ADK/Gemini enrichment agent.
- Defining a fixed taxonomy of concept `type`s (OKF is intentionally open; consumers tolerate unknown types).
- Serving/hosting infrastructure — a bundle is just files (git, tarball, static server).
- Replacing domain schemas (Avro, OpenAPI, …) — OKF *references* them.

---

## 4. Key design decisions

Four decisions were settled with the owner; everything below follows from them.

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | **Domain scope** | General wiki; BigQuery/catalog is the **first adapter**, not the center | Honors the Karpathy general-knowledge vision and the `llm-wiki` framing while preserving the reference repo's BigQuery strength as one pluggable source. |
| 2 | **Upstream code** | **Vendor the mechanics** verbatim (visualizer, `BigQuerySource`, document model, index synth); enrichment/web/lint/query stay **native to Claude** | The upstream *agent* only knows BigQuery — it can't ingest a PDF or article, so it can't serve a general wiki; and wrapping it would make Gemini the author and Claude a launcher. Its *mechanics* are pure, tested code worth reusing. Not on PyPI → vendor a copy rather than depend on `main`. |
| 3 | **Automation** | **Enforce conformance only** — hard-block writes failing §9; index/log regeneration is **manual** | Conformance is the cheap, high-value guard (a doc missing `type` is just broken OKF; blocking it is like a type error). Broad auto-editing of many index/log files on every session-end is the genuinely intrusive part — left to explicit commands. |
| 4 | **Interaction** | **Supervised, configurable** — one source at a time, review between; `--auto` for batch; per-concept fan-out *within* a source | Matches Karpathy's stated preference ("ingest one at a time, stay involved") while allowing unattended batch when wanted. |

---

## 5. Architecture overview

### 5.1 Layer mapping (Karpathy → OKF → Claude Code)

| Karpathy layer / op | OKF artifact | Claude Code primitive |
|---|---|---|
| The "schema" (disciplining doc) | bundle conventions | per-bundle `CLAUDE.md` written by `/llm-wiki:init` + plugin **skills** |
| Raw sources (immutable) | optional `raw/` | read-only inputs to ingest |
| The wiki | concept docs + `references/` | **skills** + **subagents** author them |
| Ingest | new/updated concepts | `/llm-wiki:ingest` → `authoring-concepts`, `ingest/references/web.md` |
| Query | answer filed back as a page | `query` skill |
| Lint | bundle health | `/llm-wiki:lint` → `lint/references/semantic-audit.md` + `okf_stats.py` |
| `index.md` / `log.md` | reserved files (§6/§7) | `okf_index.py` + `/llm-wiki:log` (manual, per Decision 3) |
| Conformance (§9) | `type` present, valid frontmatter | **PostToolUse hook** + `okf_validate.py` |

### 5.2 The deterministic / agentic split

- **Deterministic (scripts, no LLM):** doc I/O + validation + augmentation guard, §9 conformance, index regeneration, the HTML visualizer, capped web fetch, BigQuery metadata extraction, search, stats. These are vendored-or-new Python and are unit-testable against the three reference bundles as fixtures.
- **Agentic (skills + subagents, native Claude):** deciding what to ingest, writing prose, choosing cross-links, the web-crawl reference/enrich/skip judgment, lint findings, query synthesis.

### 5.3 Directory layout

`V` = vendored verbatim from `knowledge-catalog/okf` · `N` = new · `*` = native Claude (no script)

```
llm-wiki/                               # plugin root  ·  marketplace name == dir
├── .claude-plugin/plugin.json
├── skills/     (also the slash-command surface: /llm-wiki:<name>)
│   ├── init/                      *    scaffold a bundle + install discovery
│   ├── ingest/                    *    supervised ingest loop + adapter contract + per-concept dispatch
│   │   └── references/            *    bigquery.md · web.md (crawl + 4 gates) · re-enrich.md
│   ├── authoring-concepts/        *    write ONE conformant doc (general; catalog sections optional)
│   │   └── references/okf-spec.md N    distilled OKF v0.1 rules (ground truth)
│   ├── query/                     *    query + file-answer-back
│   │   └── references/            *    finding-sources.md (what to ingest for a gap)
│   ├── lint/                      *    stats + conformance + semantic audit → fix-it report
│   │   └── references/            *    semantic-audit.md (the deep read)
│   ├── validate/  index/          N    thin wrappers over okf_validate.py / okf_index.py
│   └── log/  visualize/           N    log.md append · okf_visualize.py
├── (no agents/ — see §6.3)
├── scripts/
│   ├── okf_lib/                   V    document.py (model) + paths.py (concept-id logic)
│   ├── okf_doc.py                 V    doc I/O + write validation + augmentation guard
│   ├── okf_validate.py            N    §9 conformance checker (command AND hook)
│   ├── okf_index.py               V    bundle/index.py + synthesizer.py (Gemini descriptions optional)
│   ├── okf_visualize.py + viewer/ V    generator.py + viz.html / viz.css / viz.js
│   ├── okf_fetch.py               V    web/fetcher.py + host/path/depth/page caps from web_tools
│   ├── okf_bq.py                  V    sources/bigquery.py + base.py → JSON CLI
│   ├── okf_search.py              N    index-first lookup + grep/BM25 fallback
│   ├── okf_stats.py               N    counts · orphans · broken links · citation coverage
│   └── requirements.txt
├── hooks/hooks.json   PostToolUse(Write|Edit, *.md) → okf_validate.py --file; block on failure
├── templates/   bundle-CLAUDE.md · root-index.md · seeds.example.txt
└── README.md
```

---

## 6. Component design

### 6.1 Skills (the knowledge layer)

Skills carry the workflows that were *system prompts* in the ADK agent, generalized and spec-grounded. They auto-trigger from natural language and are invoked by commands.

| Skill | Responsibility | Provenance |
|---|---|---|
| **authoring-concepts → `references/okf-spec.md`** | Distilled OKF v0.1 rules as ground truth (required `type`; recommended `title/description/resource/tags/timestamp`; reserved files; cross-link forms; citations; conformance; `okf_version`). Read when the question is about the format. | `SPEC.md` §3–§11 |
| **authoring-concepts** | How to write **one** conformant doc: frontmatter, body order (prose → conventional `# Schema`/`# Examples`/`# Citations`), file-relative cross-links, "don't invent fields/targets", "don't over-link". Data-catalog sections (`# Schema`, `# Common query patterns`) are an **optional domain pattern**, not the default. | `enrichment_instruction.md` (generalized) |
| **ingest** | The supervised ingest loop: detect source → adapter lists concepts → review plan → fan out enrichers → review diff → suggest `/llm-wiki:index` + `/llm-wiki:log`. Documents the **adapter contract** (§7). | `runner.py` + Karpathy "Ingest" |
| **ingest → `references/web.md`** | Self-driven crawl: seeds → follow authoritative links → **enrich vs. mint reference vs. skip**, the **four-gate reference test**, required extractions (**metrics → `references/metrics/`, joins → `references/joins/`, dimensions**), strict **augmentation rules**. | `web_ingestion_instruction.md` (port near-verbatim) |
| **ingest → `references/bigquery.md`** | First adapter: list datasets/tables (detect sharded `_YYYYMMDD` families), pull schema/partitioning/clustering via `okf_bq.py`, sample rows when sparse, one doc per concept. | `bigquery.py` + `source_tools.py` |
| **lint → `references/semantic-audit.md`** | Semantic health (Karpathy "Lint"): contradictions, stale claims, orphan pages, concepts mentioned-but-unwritten, missing cross-refs, data gaps → suggested questions/sources. Pairs with `okf_stats.py` for the mechanical findings. | Karpathy "Lint" |
| **query** | Read `index.md` first → drill in → synthesize **with citations** → offer to **file the answer back** as a new concept so explorations compound. | Karpathy "Query" |

> **2026-08-13 — consolidated 18 skills → 9.** The knowledge layer above and the
> command surface in §6.2 had grown as two parallel sets of skills describing the
> same operations: `ingest`/`ingesting-sources`, `query`/`querying-okf`,
> `lint`/`maintaining-okf`, plus `stats` and `validate` (steps 1–2 of `lint`) and
> `enrich` (the ingest loop minus the adapter). Every skill description loads in
> every session, so the duplication cost context on every turn while giving the
> model two competing places to look. The rule now is **one skill per user-facing
> operation**; source-specific and deep-detail material is a `references/` file
> under the skill that owns it, loaded only when that path is taken. `agy plugin
> install` copies `references/` intact (verified 2026-08-13), so the shape works
> on both runtimes. Retired: `okf-spec`, `ingesting-sources`, `ingesting-web`,
> `ingesting-bigquery`, `maintaining-okf`, `querying-okf`, `finding-sources`,
> `enrich`, `stats`.

### 6.2 Commands (the verb surface)

Thin entry points (mostly "activate skill X / dispatch agent Y with these args"), so the workflow works whether typed as `/llm-wiki:…` or asked in prose.

| Command | Behavior |
|---|---|
| `/llm-wiki:init [dir]` | Scaffold a bundle: root `index.md` with `okf_version: "0.1"` frontmatter, per-bundle `CLAUDE.md` (the schema layer), `.gitignore`, optional `raw/`. |
| `/llm-wiki:ingest <source…> [--auto]` | Detect source → pick adapter → **supervised** enrich (Decision 4). `--auto` fans out unattended. |
| `/llm-wiki:ingest --re-enrich [concept…]` | (Re)enrich named concepts or all, from each concept's recorded `resource`; per-concept dispatch as above. |
| `/llm-wiki:index` | Regenerate every `index.md` (`okf_index.py`); model may refine directory descriptions. |
| `/llm-wiki:lint [--quick]` | `okf_stats.py` + `okf_validate.py` + the semantic audit → fix-it report. `--quick` is mechanical stats only. |
| `/llm-wiki:query <q>` | Cited answer from the bundle; offer to file it back. |
| `/llm-wiki:validate` | §9 conformance over the whole bundle (`okf_validate.py`); non-zero exit on violation. |
| `/llm-wiki:visualize [--out --name]` | Self-contained `viz.html` (`okf_visualize.py`). |
| `/llm-wiki:log <entry>` | Append a dated `log.md` entry (manual, per Decision 3). |

### 6.3 Agents (isolated-context workers) — RETIRED, converted to skills in 0.1.7

> **2026-07-23:** This layer no longer ships. Antigravity installs plugin agents
> but cannot invoke them (`agy agents` lists nothing; a live session answers
> "NO PLUGIN SUBAGENTS"), so a component that only works on one runtime became a
> component that works on neither reliably. Each agent's procedure is now a skill
> — one copy both runtimes run, so they cannot drift:
>
> | Former agent | Now |
> |---|---|
> | `okf-concept-enricher` | the `authoring-concepts` skill, one doc per concept |
> | `okf-web-crawler` | `ingest/references/web.md` (it already held the crawl procedure) |
> | `okf-linter` | `lint/references/semantic-audit.md` |
> | `okf-source-scout` | `query/references/finding-sources.md` (it had no caller) |
>
> The isolated-context *parallelism* the agents provided is now a dispatch choice
> inside those skills: on Claude Code, fan out one `general-purpose` subagent per
> unit; on Antigravity, run sequentially. See `ingest` § Per-concept dispatch. The original design rationale is kept below for history.

Used where work is **parallelizable** (per-concept fan-out over a 30-table dataset would blow main context) or **long/deep** (a web crawl, a full audit).

| Agent | Mirrors | Why a subagent |
|---|---|---|
| **okf-concept-enricher** | per-concept ADK agent (`enrich_concept`) | One concept in → one guarded write out via `okf_doc.py`. Dispatch N in parallel; clean context each. |
| **okf-web-crawler** | web-pass ADK agent (`run_web_pass`) | Long, many fetches, much discarded content; budget enforced by `okf_fetch.py`. |
| **okf-linter** | (new) | Deep read of the whole bundle → structured findings only. |
| **okf-source-scout** | (new) | Given a gap/concept, propose authoritative seed URLs for `/llm-wiki:ingest`. |

### 6.4 Scripts (deterministic core)

Python 3. Vendored modules keep their upstream behavior; new modules are built on `okf_lib`. CLI contracts:

| Script | CLI contract | Provenance |
|---|---|---|
| **okf_lib/** | `OKFDocument.parse/serialize/validate` (required keys `type,title,description,timestamp`; key order `type,resource,title,description,tags,timestamp`; YAML `safe_dump(sort_keys=False, allow_unicode=True)`). `parse_concept_id` / `concept_id_to_path` / `path_to_concept_id` (segment regex `[A-Za-z0-9_][A-Za-z0-9_.\-]*`). | `document.py`, `paths.py` |
| **okf_doc.py** | `read <root> <id>` → `{frontmatter,body}`\|null · `write <root> <id>` (reads `{frontmatter,body}` JSON on stdin) → fills `timestamp` (UTC ISO-8601), reorders keys, applies **augmentation guard** (refuse a write that shrinks an existing table's `# Schema` field set or `# Citations` count unless `--allow-shrink`), creates dirs → `{path,bytes}`\|`{error}`. | `bundle_tools.py` |
| **okf_validate.py** | `<root> [--file <path>]` → assert every non-reserved `.md` has parseable frontmatter with non-empty `type`; check reserved-file shape + `okf_version`. Exit ≠0 on violation. `--file` mode (single doc) for the hook. | spec §9 (new) |
| **okf_index.py** | `<root> [--no-llm]` → bottom-up `index.md` regeneration: group entries by `type`, pull each `description` from frontmatter, emit `* [title](link) - desc`; directory descriptions via Gemini Flash, or deterministic `Contains N entries…` with `--no-llm`. | `index.py`, `synthesizer.py` |
| **okf_visualize.py** | `<root> [--out <p>] [--name <s>]` → walk concepts, extract internal `.md` links, build type-colored nodes + link edges + cited-by backlinks, inline into `viewer/viz.html` → `{concepts,edges,bytes}`. Output HTML needs **zero** runtime deps (Cytoscape + marked from CDN). | `generator.py`, `viewer/` |
| **okf_fetch.py** | `<url> --state <f.json> [--allowed-host H]… [--allowed-path-prefix P]… [--denied-path-substring S]… [--max-depth N] [--max-pages N]` → `{url,title,markdown,links,depth,fetched_count}`\|`{error}`. Enforces scheme/host/path/depth/page-budget against the session **state file** so the crawler **cannot overrun**. | `fetcher.py`, `web_tools.py` |
| **okf_bq.py** | `list <project.dataset>` · `describe <project.dataset> <id>` · `sample <project.dataset> <id> [-n N]` → JSON. Shard-family detection (`^(.+?_)(\d{6,8})$`); billing from ADC or `--billing-project`. | `bigquery.py`, `base.py` |
| **okf_search.py** | `<root> <query> [--k N]` → ranked hits; index-first, grep/BM25 fallback; optional qmd hand-off if present. | gist "CLI tools" (new) |
| **okf_stats.py** | `<root>` → `{by_type, links, orphans, broken_links, citation_coverage}`. | (new) |
| **okf_discover.py** | `<root> [--host DIR] [--check\|--sync] [--create]` → install/refresh the bundle's discovery block in the host repo's briefing files, one mode per file (`@` import for a standalone `CLAUDE.md`, inlined catalog otherwise). Owns only the region between its `<!-- llm-wiki:discovery <rel> -->` markers; `--check` exits 1 when missing or stale. | (new) |

### 6.5 Hooks

Per Decision 3, exactly one hook. `hooks/hooks.json`:

- **PostToolUse**, matcher `Write|Edit`, fires when the edited path is `*.md` under a bundle → runs `okf_validate.py <root> --file <changed>`. On non-zero exit, returns a **blocking** decision with the validator's error so Claude fixes the doc before the turn ends. This is the hook equivalent of the upstream `write_concept_doc` validation, enforcing §9 on every write.
- **No** Stop/SubagentStop auto-regeneration; **no** SessionStart side effects. Session-start orientation was considered as a hook and is instead handled by `okf_discover.py` writing the host briefing file (§8.1) — the briefing file is loaded by both runtimes for free, whereas Antigravity has no `SessionStart` event at all and its `PreInvocation` substitute blocks every turn.

### 6.6 Templates

- **`bundle-CLAUDE.md`** — the per-bundle "schema" file (`/llm-wiki:init` writes it): directory conventions, the `type` vocabulary in use, the citation style, the ingest/lint workflow for *this* bundle. Generic plugin skills stay reusable; this file specializes them per bundle, and the owner co-evolves it.
- **`root-index.md`** — root index seeded with `okf_version: "0.1"` frontmatter (the one place §6/§11 permit frontmatter in an `index.md`).
- **`seeds.example.txt`** — commented seed-URL file for the web pass (mirrors the reference `samples/*/seeds.txt`).

---

## 7. The source-adapter seam

Since the core is a general wiki with structured sources as adapters (Decision 1), every source plugs in through one uniform contract, mirroring the upstream `Source` ABC (`list_concepts` / `read_concept` / `sample_rows` / `find`):

| Adapter provides | Meaning | BigQuery (first impl) |
|---|---|---|
| `list_concepts` | candidate concept ids + `type`s (+ resource, hint) | datasets/tables, shard-family detection → `okf_bq.py list` |
| `describe(concept)` | raw structured metadata | schema/partitioning/clustering JSON → `okf_bq.py describe` |
| `sample(concept)` *(optional)* | a few example rows when metadata is sparse | `okf_bq.py sample` |

An adapter = a **skill** (routing/judgment) + an optional **script** (deterministic metadata pull). `authoring-concepts` turns that raw metadata into conformant OKF prose the same way regardless of source. **Adding a source** (a PDF folder, a Git repo, an OpenAPI spec, Postgres) is one new `ingesting-<x>` skill (+ optional `okf_<x>.py`) — no core changes.

---

## 8. Key workflows

### 8.1 Init

`/llm-wiki:init research/llms` → scaffold bundle, write the per-bundle `CLAUDE.md`, root `index.md` (`okf_version: "0.1"`), `.gitignore`, optional `raw/`, then **install discovery** in the host repo's briefing files.

Discovery is the step that decides whether any of the rest matters. A prose pointer does not fire — "I am about to re-derive something the wiki covers" is not a state an agent recognises about itself (observed failing over a full session, `local-minions`, 2026-07-21). What fires is content the harness loads unconditionally: the briefing file. The runtimes disagree on which file that is and whether `@` imports expand (Claude Code 2.1.218: `CLAUDE.md`, imports yes, `AGENTS.md` never read; `agy` 1.1.5: `AGENTS.md`/`GEMINI.md`, imports no), so `okf_discover.py` chooses per file and `/llm-wiki:index` re-syncs the inlined copies.

### 8.2 Supervised ingest (default)

```
/llm-wiki:ingest <source>
  1. Detect source → pick adapter (url→web · file/dir→docs · project.dataset→bq · repo→git)
  2. Adapter lists candidate concepts → show the plan (create/update) → owner confirms/adjusts
  3. Fan out okf-concept-enricher subagents for THIS source's concepts
       └ each write goes through okf_doc.py (guarded) → PostToolUse hook re-validates
  4. Present a diff summary of touched docs → owner reviews
  5. Proceed to the next source only on the owner's go
  6. Suggest `/llm-wiki:index` + `/llm-wiki:log`   (manual, per Decision 3)

/llm-wiki:ingest <sources…> --auto   → skip pauses; fan out across everything; one review at the end
```

### 8.3 Web ingest

`ingest/references/web.md` + `okf-web-crawler`: seeds → `okf_fetch.py` (budget-capped) → per page, **enrich** existing docs or **mint** `references/…` per the four-gate test; metrics/joins land in `references/metrics/` and `references/joins/`; augmentation rules preserve existing structure.

### 8.4 Index / validate / visualize

`/llm-wiki:index` (regenerate), `/llm-wiki:validate` (§9), `/llm-wiki:visualize` (HTML graph) — all deterministic scripts.

### 8.5 Lint

`/llm-wiki:lint` → `okf-linter` (semantic: contradictions, staleness, orphans) + `okf_stats.py` (mechanical: broken links, citation coverage) → a prioritized fix-it report.

### 8.6 Query

`/llm-wiki:query "how does X compare to Y?"` → read index → drill in → cited synthesis → offer to file `concepts/x-vs-y.md` back into the bundle.

---

## 9. Conformance & the augmentation guard

- **Conformance (§9)** is enforced two ways: `okf_doc.py write` validates required frontmatter before writing, and the **PostToolUse hook** re-runs `okf_validate.py --file` on *any* markdown write (including hand edits), blocking non-conformant docs. `/llm-wiki:validate` checks the whole bundle on demand.
- **Augmentation guard** (from the web pass) lives in both layers: `okf_doc.py` deterministically refuses a write that shrinks an existing table's `# Schema` field set or drops `# Citations` (hard guard), and `ingest/references/web.md` carries the augmentation rules as instructions (soft guard) — preserve every `#` heading, merge tags, keep `resource` verbatim, put the web URL in `# Citations` not `resource`.

---

## 10. Dependencies & install

Scripts ship a `requirements.txt`; heavy deps are **feature-gated**, so a text-only general wiki installs almost nothing:

| Dependency | Needed for | Notes |
|---|---|---|
| `pyyaml` | always (doc model) | the only universal dep |
| `markdownify` | web ingest (`okf_fetch.py`) | HTML→markdown |
| `google-cloud-bigquery` | BigQuery adapter only | ADC for auth |
| `google-genai` | *optional* `okf_index.py` directory descriptions | deterministic `--no-llm` fallback works without it; Claude can upgrade descriptions natively |

**No `google-adk`** — the agent harness is replaced by Claude. The visualizer's *output* has zero runtime deps (CDN libs at view time). Vendored upstream files retain their Apache-2.0 license headers; `LICENSE`/attribution noted in the plugin `README`.

---

## 11. Data model (the doc contract)

- **Concept doc** = YAML frontmatter (`---`-delimited) + markdown body. Required: `type`. Recommended: `title`, `description` (one sentence; used verbatim in `index.md`), `resource`, `tags`, `timestamp`.
- **Serialization** (vendored): frontmatter keys ordered `type, resource, title, description, tags, timestamp` then extras; `yaml.safe_dump(sort_keys=False, allow_unicode=True)`; body ensured to end with `\n`. `timestamp` auto-filled to UTC ISO-8601 (`timespec="seconds"`) when absent.
- **Concept ID** = file path minus `.md` (e.g. `tables/users.md` → `tables/users`); segments match `[A-Za-z0-9_][A-Za-z0-9_.\-]*`.
- **Reserved files**: `index.md` (no frontmatter, except `okf_version` at bundle root), `log.md` (date-grouped `## YYYY-MM-DD` entries, newest first).
- **Cross-links**: plain markdown; spec recommends bundle-relative `/path`, but the reference producer uses **file-relative** links for GitHub rendering — `authoring-concepts` standardizes on file-relative and documents the trade-off.

---

## 12. Build plan (phased)

**Phase 0 — deterministic spine.** Vendor `okf_lib`, `okf_doc.py`, `okf_index.py`, `okf_visualize.py` (+ `viewer/`); write new `okf_validate.py`. Unit-test against the three reference bundles (`ga4`, `stackoverflow`, `crypto_bitcoin`) as known-good fixtures.

**Phase 1 — author + guard (MVP).** `okf-spec` + `authoring-concepts` skills; `/llm-wiki:init` (+ templates); `/llm-wiki:validate`, `/llm-wiki:index`, `/llm-wiki:visualize`; the PostToolUse conformance hook. → usable *hand-author → guardrail → index → visualize* loop.

**Phase 2 — ingest loop.** `ingesting-sources` + `ingesting-web` skills; `okf-concept-enricher` + `okf-web-crawler` agents; `okf_fetch.py`; `/llm-wiki:ingest` (supervised + `--auto`), `/llm-wiki:enrich`, `/llm-wiki:log`.

**Phase 3 — maintain, query, first adapter.** `maintaining-okf` + `querying-okf` skills; `okf-linter`, `okf-source-scout`; `okf_search.py`, `okf_stats.py`; `/llm-wiki:lint`, `/llm-wiki:query`, `/llm-wiki:stats`; then `ingesting-bigquery` + `okf_bq.py` as the first structured adapter. Register the `llm-wiki` plugin in `marketplace.json` (`name: llm-wiki`, `source: ./llm-wiki`).

---

## 13. Open questions

1. **`raw/` sources layer.** Adopt Karpathy's immutable `raw/` convention inside the bundle, or treat sources as ephemeral inputs? Leaning: support `raw/` optionally via `/llm-wiki:init`, don't require it.
2. **Single- vs multi-bundle repos.** Reference repo nests `bundles/<name>/`. Decide how commands/hook locate the bundle root (nearest ancestor with a root `index.md`?).
3. **Directory-description model.** Keep `google-genai` (Gemini Flash) for `okf_index.py` descriptions, or have Claude write them and drop the optional dep entirely? Leaning: ship `--no-llm` default, let Claude upgrade.

---

## Appendix A — Provenance map

| Plugin component | Upstream source (`knowledge-catalog/okf`) |
|---|---|
| `okf_lib/` | `src/enrichment_agent/bundle/document.py`, `bundle/paths.py` |
| `okf_doc.py` | `bundle/document.py` + `tools/bundle_tools.py` (write/validate/augment) |
| `okf_index.py` | `bundle/index.py` + `bundle/synthesizer.py` |
| `okf_visualize.py` + `viewer/` | `viewer/generator.py` + `viewer/templates/viz.html` + `viewer/static/{viz.css,viz.js}` |
| `okf_fetch.py` | `web/fetcher.py` + `tools/web_tools.py` (caps) |
| `okf_bq.py` | `sources/bigquery.py` + `sources/base.py` |
| `ingesting-web` skill | `prompts/web_ingestion_instruction.md` |
| `authoring-concepts` skill | `prompts/enrichment_instruction.md` |
| `ingesting-sources` / ingest flow | `runner.py` (`enrich_all` two-pass) |
| `okf_validate.py` | new — implements spec §9 |

## Appendix B — References

- OKF v0.1 spec — `GoogleCloudPlatform/knowledge-catalog/okf/SPEC.md`
- Reference implementation & sample bundles — `GoogleCloudPlatform/knowledge-catalog/okf/`
- "LLM Wiki" pattern — Karpathy gist `442a6bf555914893e9891c11519de94f`
- Claude Code plugin authoring — `plugin-dev` skills (plugin-structure, skill-development, agent-development, hook-development, command-development)
