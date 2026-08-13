---
name: authoring-concepts
description: Use when writing or rewriting a single OKF concept document, or when you need the OKF v0.1 format rules — frontmatter conventions, concept IDs, reserved files, body structure, cross-linking, citation format, and what NOT to invent. The shared authoring routine that ingest, query, and lint all call.
---

# Authoring OKF Concept Docs

You are writing **one** conformant OKF document. This skill is the authoring
workflow and body conventions; the format rules it conforms to are in
**`references/okf-spec.md`** — read that when the question is about the format
itself (concept IDs, reserved files, conformance §9, the frontmatter contract).

## Workflow

1. **Check for an existing doc.** Run `python3 <plugin_root>/scripts/okf_doc.py read <bundle_root> <concept_id>`. If a doc exists, use it as the starting point — refine rather than rewrite.
2. **Gather raw material.** Read source files, inspect metadata, or use adapter scripts (`okf_bq.py describe`, etc.) to get structured data.
3. **Survey the bundle.** Skim `index.md` files and the `CLAUDE.md` at the bundle root to understand the existing `type` vocabulary and cross-link targets.
4. **Compose the document.** See body structure below.
5. **Write via the script.** Run `echo '<JSON>' | python3 <plugin_root>/scripts/okf_doc.py write <bundle_root> <concept_id>`. Do NOT hand-write YAML frontmatter directly — the script fills `timestamp`, reorders keys, validates, and applies the augmentation guard.

## Frontmatter

Required keys: `type`, `title`, `description`, `timestamp` (auto-filled — omit or set to empty).
Recommended: `resource` (URI of underlying asset), `tags` (YAML list).

```yaml
---
type: Article          # required; match your bundle's type vocabulary
resource: https://...  # source URI when applicable
title: Short Display Name
description: One tight sentence used verbatim in index.md.
tags: [topic, subtopic]
timestamp:             # leave blank; okf_doc.py fills UTC ISO-8601
---
```

## Body structure

Write in this order (skip sections that don't apply):

1. **Prose introduction** (1–3 paragraphs) — what this concept is, what it represents, how it is typically used. For data tables: describe the grain (one row per X), time range, and any sampling or obfuscation caveats.

2. **`# Schema`** (data-catalog docs) — a readable summary of fields. For nested RECORD fields, indent or table-format their sub-fields. Skip mode/type when obvious. Highlight repeated records explicitly. Format field names in backticks so the augmentation guard can track them.

3. **`# Common query patterns`** (data-catalog docs) — 1–3 short `sql` fenced blocks illustrating realistic usage.

4. **`# Examples`** (general docs) — concrete examples, code snippets, or illustrations.

5. **`# Citations`** — numbered references. Always include the `resource` URL (if any) as `[1]`. Only cite URLs you actually know.

```markdown
# Citations

[1] [BigQuery REST API](https://bigquery.googleapis.com/v2/...)
[2] [Schema Reference](https://example.com/schema)
```

## Cross-linking

After step 3, look at the available concept IDs (from `index.md`) and add file-relative links where your prose naturally names another concept:

```markdown
# From tables/events.md:
[users table](users.md)
[dataset](../datasets/my_dataset.md)
[DAU metric](../references/metrics/dau.md)
```

**Rules:**
- File-relative paths only. Never start a link with `/`.
- Only link to concept IDs that actually exist in the bundle.
- One link per concept mention per section — don't over-link.
- Don't link from headers, fenced code blocks, or field-name listings.
- Don't link the current doc to itself.

## Style

- Be concrete: use real field names, real enum values, real example queries.
- Do not invent fields, partitions, or shard counts not in the source data.
- No preamble, apologies, or reasoning narration in the body — valid markdown only.
- Prose for general knowledge; `# Schema` and `# Common query patterns` are optional domain patterns for data-catalog docs, not defaults for every concept type.

## Writing via `okf_doc.py`

The JSON payload for `write`:
```json
{
  "frontmatter": {
    "type": "Article",
    "title": "My Concept",
    "description": "One sentence.",
    "resource": "https://...",
    "tags": ["topic"]
  },
  "body": "Prose here.\n\n# Citations\n\n[1] [Source](https://...)\n"
}
```

The script validates frontmatter, auto-fills `timestamp`, reorders keys, and applies the augmentation guard before writing. An `{"error": "..."}` response means the write was refused — read the reason and fix it.
