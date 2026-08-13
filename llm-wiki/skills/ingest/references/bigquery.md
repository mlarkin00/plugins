# BigQuery Adapter for OKF Ingest

The first structured source adapter, loaded by `/llm-wiki:ingest <project.dataset>`.
It translates a BigQuery dataset into OKF concept docs (one per dataset and one
per table/shard-family).

Requires: `google-cloud-bigquery` pip package + Application Default Credentials.

## Prerequisites

```bash
gcloud auth application-default login
pip install google-cloud-bigquery
```

## Step 1 — List concepts

```bash
python3 <plugin_root>/scripts/okf_bq.py list <project.dataset> [--billing-project P]
```

Output: JSON array of concept refs:
```json
[
  {"id": "datasets/<name>", "type": "BigQuery Dataset", "resource": "...", "hint": {...}},
  {"id": "tables/<name>", "type": "BigQuery Table", "resource": "...", "hint": {"wildcard": false, "table_id": "..."}},
  {"id": "tables/<prefix>", "type": "BigQuery Table", "resource": "...", "hint": {"wildcard": true, "family_prefix": "...", "shard_count": N, "first_shard": "...", "last_shard": "..."}}
]
```

**Shard-family detection**: Tables matching `<prefix>_YYYYMMDD` (6–8 digit suffix) are collapsed into one concept with `wildcard: true`. The representative shard (latest) is used for schema inspection. The concept ID uses the prefix ending with `_` (e.g. `tables/events_` for `events_20240101`, `events_20240102`, …).

Present the concept list to the owner and let them trim or adjust before proceeding.

## Step 2 — Describe each concept

For each concept to enrich:

```bash
python3 <plugin_root>/scripts/okf_bq.py describe <project.dataset> <id> [--billing-project P]
```

Returns JSON with schema, partitioning, clustering, row counts, labels, etc.

For sparse metadata (no description, few fields), optionally sample rows:

```bash
python3 <plugin_root>/scripts/okf_bq.py sample <project.dataset> <id> [-n 3] [--billing-project P]
```

Note: sampling very large tables (`transactions` in crypto_bitcoin is hundreds of GB) incurs query costs. Keep `-n` small while iterating.

## Step 3 — Enrich via authoring-concepts

Author each concept by following `authoring-concepts`, passing the raw metadata below. For many concepts, dispatch per the runtime (see the parent `SKILL.md` § Per-concept dispatch): parallel subagents on Claude Code, sequential on Antigravity. The metadata shape guides the body:

**For BigQuery Dataset**:
- `type: BigQuery Dataset`
- `resource`: the BQ REST URI from the concept ref
- Body: what the dataset is, where it comes from, location, labels, creation/modification dates, link to the child tables.

**For BigQuery Table (singleton)**:
- `type: BigQuery Table`
- `resource`: the BQ REST URI
- Body: grain (one row per X), time range, `# Schema` with all fields in backticks, `# Common query patterns`, `# Citations`.

**For BigQuery Table (shard family)**:
- Same as singleton but note the shard pattern (e.g. `events_YYYYMMDD`), shard count, first/last shard, and wildcard syntax for cross-dataset queries.

## Augmentation guard awareness

When re-enriching an existing BigQuery Table doc (e.g. after a schema change), `okf_doc.py write --web-pass` applies the augmentation guard. To intentionally shrink the `# Schema` section (e.g. the table schema was reduced upstream), use `--allow-shrink` and document the schema change in `# Citations`.

## Cross-linking

After enriching all concepts in a dataset:
1. Each table doc should cross-link to its parent dataset doc: `[dataset](../datasets/<name>.md)` (file-relative from `tables/`).
2. Related tables should cross-link to each other where natural.
3. After ingesting, run `/llm-wiki:index` to regenerate `index.md` files.
