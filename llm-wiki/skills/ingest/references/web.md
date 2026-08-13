# Web Ingestion into an OKF Bundle

Port of `knowledge-catalog/okf/src/enrichment_agent/prompts/web_ingestion_instruction.md`.

Loaded by `/llm-wiki:ingest <url>` or `/llm-wiki:ingest seeds.txt`. This is the
full crawl procedure — the workflow, gates, and augmentation rules below are
everything the retired `okf-web-crawler` agent did. Drive it with
`okf_fetch.py`, whose state file caps the page budget so the crawl cannot run
away. On Claude Code you may dispatch the crawl into a `general-purpose` subagent
to isolate a long multi-page run; on Antigravity (no dispatchable subagents) run
it inline. A single URL is always fine to do inline.

## Workflow

1. Initialize the fetch state file:
   ```bash
   python3 <plugin_root>/scripts/okf_fetch.py <seed_url> \
     --state /tmp/okf-crawl-state.json --seed \
     --max-pages 100 --max-depth 2
   ```
2. Read the current bundle: `list_concepts` by reading the bundle's `index.md` hierarchy. Know what concepts exist before fetching.
3. For each seed, fetch with `okf_fetch.py <url> --state <f.json>`. The result includes `markdown`, `links`, `depth`, `fetched_count`.
4. From the links, pick a small handful that look like **authoritative documentation** on topics related to existing concepts. Skip: nav links, footers, login pages, "About us", marketing, cookie/privacy, anything obviously tangential.
5. For each page fetched, decide:

### Decision A — Enrich existing concept

The page describes a topic an existing concept doc already covers. Read the existing doc with `okf_doc.py read`, then write the augmented doc with `okf_doc.py write --web-pass`.

See **Augmentation rules** below — they are non-negotiable.

### Decision B — Mint a new `references/` doc

Only if the page meets **all four** of:

1. **Topic shape**: defines something *referenceable by name* — a business entity definition, a metric, an enum/status-code reference, a field/parameter glossary, a pricing/billing note, a units/timezone/identifier convention.
2. **Not bundle-level meta**: NOT an overview, intro, getting-started, quickstart, tutorial, walkthrough, release-notes, changelog, roadmap, FAQ, or product landing page. If the title or URL slug contains `overview`, `intro`, `getting-started`, `quickstart`, `tutorial`, `walkthrough`, `release-notes`, `changelog`, `roadmap`, `faq` — **skip**.
3. **Citation test**: you can write a sentence in a primary concept doc of the form `See the [X reference](../references/x.md) for ...` where X is a concrete noun. If the best sentence is "See the overview for context", it fails.
4. **Reuse test**: at least two existing concepts would benefit from citing it, OR one concept needs it as load-bearing background that doesn't fit in the concept's own doc.

If all four hold: pick a concept ID under `references/` (e.g. `references/event_parameters`), set `type: Reference`, `resource` to the page URL, write via `okf_doc.py write`, then cross-link from each related primary doc with a **file-relative** link.

When in doubt, **skip**. A bundle with zero `references/` docs is fine.

### Decision C — Skip

Irrelevant, low-signal, or already covered. Move on.

## Required extractions (bypass the four-gate test)

When a fetched page contains any of the following, capture them — these are the highest-signal artifacts:

**Aggregate metrics** (DAU, conversion rate, revenue per user, etc.):
- One `references/metrics/<slug>.md` per metric: `type: Reference`, `tags: [metric]`, `resource` = page URL, body = one-sentence definition + fenced SQL formula + `# Citations`.
- Add a `# Metrics` section to each contributing concept doc linking to the reference.
- Do NOT duplicate the SQL in the primary doc; the reference owns it.

**Dimensions** (filterable/groupable attributes — `GROUP BY`/`WHERE` columns):
- Add semantic description inline to the relevant concept's `# Schema` section, OR add a `# Dimensions` subsection.
- For shared enum values across multiple tables, mint `references/<slug>.md` and cite from each.

**Join paths** (explicit FK relationships between tables):
- One `references/joins/<a>__<b>.md` per pair (table names sorted alphabetically, double underscore). `type: Reference`, `tags: [join]`, body = fenced SQL `ON` clause + when-to-use sentence + `# Citations`.
- Add a `# Joins` section to each side's primary doc linking to the reference.
- Do NOT invent joins — only capture joins explicitly named in docs or example queries on the fetched page.

## Augmentation rules (non-negotiable when enriching an existing doc)

1. **Frontmatter — pass the complete dict**: `okf_doc.py write` does a full replacement. You must include every key the existing doc had. Specifically:
   - Copy `type` verbatim from the existing frontmatter.
   - Copy `title` verbatim. The web page's `<title>` is NOT the concept's title.
   - Copy `resource` verbatim. For a BigQuery Table doc, `resource` is the BigQuery REST URI; it must stay.
   - For `tags`, pass the union of existing + new tags.
   - Omit `timestamp` so the script refreshes it.
   - You may refine `description` if the web page surfaces a more accurate one-sentence summary.

2. **Body — every existing `#` heading must appear in your new body**, in the same order, same wording. You may:
   - Extend prose under each heading
   - Add bullets to existing lists (e.g. new fields to `# Schema`, not replace)
   - Add new `##` sub-sections under existing top-level headings
   - Add brand-new top-level headings **after** existing ones
   - Append the page URL to `# Citations`
   You may NOT:
   - Drop or rename any existing `#` heading
   - Replace the body wholesale with a topical rewrite of the web page
   - Shrink or rewrite `# Schema` for a BigQuery Table doc (the BQ pass populated it from real metadata)

3. If you cannot honor rule 2 (the page is a fundamentally different topic), do NOT call `write`. Either mint a `references/<slug>` doc and cross-link, or skip the page.

## Frontmatter for reference docs

```yaml
type: Reference
resource: <page URL>
title: Short descriptive name
description: One tight sentence.
tags: [metric]  # or [join], [dimension], etc.
timestamp:
```

## Stop conditions

- `okf_fetch.py` returns `{"error": "max_pages reached"}` — budget spent.
- You have covered the relevant material and further fetches would have diminishing returns.

## End-of-session summary

Report: how many pages fetched, how many docs updated, how many references minted.
