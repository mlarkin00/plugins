# Finding Sources for a Knowledge Gap

Given a topic or a thin concept, find authoritative sources worth ingesting.
Read this when the bundle cannot answer a query, when `/llm-wiki:lint` reports a
data gap, or on a direct request — "where can I get data on X", "find a source
for this metric", "what should I ingest to fill this gap".

This was the `okf-source-scout` agent until llm-wiki 0.1.7, then a standalone
skill; it is reference material now because it has no caller that fans it out —
it is always run directly, in the session that found the gap.

## Inputs

- `bundle_root`: the bundle, for context on what already exists
- `topic`: the concept ID, keyword, or description of what's missing
  (e.g. "BigQuery pricing", "user lifecycle events", "event_name enum values")
- optionally, the list of existing concept IDs (from `index.md`)

## Workflow

1. **Read the bundle context** — skim the `index.md` files and the bundle's
   `CLAUDE.md` to understand the domain and the existing `type` vocabulary.

2. **Name the gap precisely.** Is it a metric definition? A join relationship?
   A dimension's enum values? A concept that exists but is under-documented?

3. **Find authoritative sources.** Prefer, in order:
   - Official vendor documentation (e.g. Google Cloud Docs for BigQuery topics).
   - Schema / reference pages, not tutorials or overviews — the four-gate test
     in `ingest/references/web.md` will reject overview pages anyway.
   - Public datasets that relate to existing sources. For BigQuery, prefer
     `bigquery-public-data` datasets — free to query (caller pays for bytes).
   Use WebSearch when you need to locate a page, and verify it looks like
   documentation before recommending it.

4. **Return recommendations** the owner can act on:

```json
{
  "topic": "GA4 event_name enum values",
  "recommendations": [
    {
      "source_type": "url",
      "value": "https://support.google.com/analytics/answer/9216061",
      "rationale": "Official GA4 event reference — lists automatically collected events.",
      "ingest_command": "/llm-wiki:ingest https://support.google.com/analytics/answer/9216061"
    },
    {
      "source_type": "bigquery",
      "value": "bigquery-public-data.ga4_obfuscated_sample_ecommerce",
      "rationale": "Public GA4 sample dataset — good for sampling event_name values in practice.",
      "ingest_command": "/llm-wiki:ingest bigquery-public-data.ga4_obfuscated_sample_ecommerce"
    }
  ],
  "notes": "Prefer the support.google.com page over the developer reference for enum values — more complete."
}
```

## Rules

- Only recommend sources you have good reason to believe exist and are
  authoritative. Do not invent URLs.
- Explain the rationale for each, so the owner can choose.
- Each recommendation ends in a ready-to-run `/llm-wiki:ingest` command.
