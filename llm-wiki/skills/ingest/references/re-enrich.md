# Re-enrich Mode — `/llm-wiki:ingest --re-enrich`

Re-runs enrichment on concepts already in the bundle, with no new source. Each
concept is re-authored by following the `authoring-concepts` skill. Useful for
refreshing stale docs after a source schema change.

## Usage

```
/llm-wiki:ingest --re-enrich [concept-id…]
```

Without concept IDs, re-enriches ALL concepts in the bundle.

## Steps

1. If concept IDs are specified, use them directly. Otherwise, walk the bundle and collect all concept IDs (from non-reserved `.md` files with a `type` field).

2. For each concept ID, read the existing doc:
   ```bash
   python3 <plugin_root>/scripts/okf_doc.py read <bundle_root> <concept_id>
   ```

3. Determine the source for fresh metadata:
   - If the concept has a `resource` URI pointing to BigQuery, use `okf_bq.py describe` (see `bigquery.md`).
   - If it points at a web page, re-fetch it and apply the augmentation rules in `web.md` — they are non-negotiable on any web-sourced write.
   - For other concepts, re-read the raw source if available in `raw/`.
   - If no live source is available, enrich from the existing doc + context alone.

4. Author each concept by following `authoring-concepts` — read existing doc, get fresh raw metadata, write the augmented doc via `okf_doc.py write` (the PostToolUse hook validates each write). Dispatch per the runtime: see the parent `SKILL.md` § Per-concept dispatch.

5. Report: N docs updated, M unchanged, any errors.

6. Suggest `/llm-wiki:index` to regenerate indexes after bulk updates.

## Limiting scope

To re-enrich just one table:
```
/llm-wiki:ingest --re-enrich tables/events_
```

To re-enrich all reference docs:
```
/llm-wiki:ingest --re-enrich references/metrics/dau references/joins/events___users
```
