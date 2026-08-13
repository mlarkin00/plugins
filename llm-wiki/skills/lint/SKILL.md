---
name: lint
description: Use when the user invokes /llm-wiki:lint or /llm-wiki:stats, or asks for a health check, statistics, orphan/broken-link counts, or a semantic audit of an OKF bundle. Runs mechanical stats via okf_stats.py, then the deep semantic audit, and produces a prioritized fix-it report.
---

# /llm-wiki:lint — Bundle Health Check

Karpathy's "Lint" operation. Combines mechanical stats (`okf_stats.py`) with a
semantic audit no script can do into a prioritized fix-it report.

## Usage

```
/llm-wiki:lint [path]           # full pass: stats + conformance + semantic audit
/llm-wiki:lint --quick [path]   # mechanical stats only, no semantic audit
```

`path` defaults to the nearest bundle root.

## Steps

1. **Mechanical stats** (always run first):
   ```bash
   python3 <plugin_root>/scripts/okf_stats.py <bundle_root>
   ```
   Output JSON:
   ```json
   {
     "total_concepts": 12,
     "by_type": {"BigQuery Dataset": 1, "BigQuery Table": 4, "Reference": 7},
     "total_links": 34,
     "orphans": ["references/metrics/ltv"],
     "broken_links": [{"from": "tables/events_", "to": "references/event_parameters"}],
     "citation_coverage": "9/12"
   }
   ```

   **With `--quick`, stop here** and present it as a readable summary:
   ```
   OKF Bundle Stats — <path>
     12 concepts: 4 BigQuery Table, 7 Reference, 1 BigQuery Dataset
     34 internal links
     1 orphan (not linked from anywhere): references/metrics/ltv
     1 broken link: tables/events_ → references/event_parameters (missing)
     Citation coverage: 9/12 (75%)
   ```
   For orphans or broken links, suggest:
   - Orphan: "Link it from a related concept, or remove it if it's no longer relevant."
   - Broken link: "Create the missing concept doc or fix the link path."

2. **Conformance check**:
   ```bash
   python3 <plugin_root>/scripts/okf_validate.py <bundle_root>
   ```

3. **Semantic audit** — follow **`references/semantic-audit.md`** for the deep
   read: what to look for, the rules that keep it honest, and the findings shape.
   On Claude Code you may dispatch it into a `general-purpose` subagent to
   isolate a large bundle read; on Antigravity run it inline.

4. **Synthesize** the combined report:

   ```
   ## OKF Bundle Health Report — <path>
   ### Stats
   - N concepts (A BigQuery Table, B Reference, ...)
   - N links, N orphans, N broken links
   - Citation coverage: N/M

   ### Critical (fix before sharing)
   [1] Broken link: tables/events_ → references/event_parameters.md (file not found)
       Fix: create the missing reference doc or remove the link.

   ### Moderate
   [2] Orphan: references/metrics/ltv.md — not linked from any concept doc.
       Fix: add a link from tables/users.md or tables/events_.md.

   ### Minor
   [3] Thin description: datasets/crypto_bitcoin.md — description is 3 words.
       Fix: expand to one tight sentence about what this dataset is.
   ```

   Severity levels:
   - **Critical**: conformance violation, broken link to a referenced concept, direct contradiction
   - **Moderate**: stale claim, missing cross-ref for a high-traffic concept, orphan with inbound mentions elsewhere
   - **Minor**: thin description, missing citation, stylistic inconsistency

5. **Offer to fix** specific Critical issues inline, or save the full report:
   > "Should I fix issue [1] now, or save this report to `concepts/lint-report-2026-06-19.md`?"

   For a **data gap** finding — a concept that is thin because the bundle never
   ingested the material — follow `query/references/finding-sources.md` to
   recommend what to ingest.

## After fixing

```
/llm-wiki:validate   — confirm all violations are resolved
/llm-wiki:index      — regenerate indexes if docs were added/removed
/llm-wiki:log        — record the lint pass
```
