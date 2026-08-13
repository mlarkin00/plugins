# The Semantic Audit

Step 3 of `/llm-wiki:lint`: the LLM reads the wiki and identifies health issues
that mechanical tools can't catch. `okf_stats.py` (step 1) already covers the
mechanical findings — orphans, broken links, citation coverage — so this pass is
purely about judgment.

It replaces the retired `okf-linter` agent; run it inline, or on Claude Code
dispatch it into a `general-purpose` subagent for an isolated read of a large
bundle. On Antigravity, run it inline (there are no dispatchable subagents).

## What to look for

**Semantic issues** (judgment required — mechanical tools can't catch these):

1. **Contradictions** — two concept docs that make conflicting claims. Example: one doc says "event_name is always lowercase" and another says "event_name preserves original casing."
2. **Stale claims** — factual assertions that may be outdated (e.g. "the schema has 12 fields" but the current schema has 15; a "current version" claim with an old timestamp).
3. **Orphan pages** — concept docs that are never cross-linked from anywhere, making them invisible in practice.
4. **Concepts mentioned but not written** — the prose in existing docs mentions a concept by name (e.g. "the `user_properties` RECORD") but no dedicated concept doc for it exists.
5. **Missing cross-references** — two related concepts that should link to each other but don't.
6. **Data gaps** — concepts with thin descriptions, no examples, no citations, or a `# Schema` that is clearly incomplete.
7. **Type inconsistencies** — the same real-world entity called different `type` values in different docs (e.g. `Reference` vs `Article` for the same kind of thing), indicating the type vocabulary has drifted.

## Audit procedure

Run this to produce the semantic findings (it is what the `okf-linter` agent
used to do):

1. **Read the root `index.md`** to understand the bundle structure.
2. **Read every concept doc**, walking subdirectories. For a large bundle
   (>50 docs), prioritize primary concept docs (tables, datasets) over
   reference docs.
3. **Identify findings** across the seven categories above. Rules that keep the
   audit honest:
   - Only report findings you are confident about from reading the docs — do not
     speculate.
   - For a **stale claim**, compare it against other evidence *in the bundle*
     (e.g. count the actual `# Schema` fields), never against your training data.
   - For a **missing concept**, only flag concepts explicitly named in existing
     prose, not concepts you think ought to exist.
4. **Return structured findings** so the caller can synthesize a report:

```json
{
  "findings": [
    {
      "severity": "critical|moderate|minor",
      "category": "contradiction|stale|orphan|missing-concept|missing-xref|data-gap|type-inconsistency",
      "concept_id": "tables/events_",
      "title": "Contradictory case-sensitivity claim",
      "description": "tables/events_.md says event_name is always lowercase, but references/event_parameters.md says it preserves original casing.",
      "suggested_fix": "Check the BigQuery schema description; likely always lowercase. Update references/event_parameters.md."
    }
  ],
  "summary": { "total": 5, "critical": 1, "moderate": 2, "minor": 2 }
}
```

## Per-finding output shape

When reporting findings back to the caller, each one is:

```
[SEVERITY] <short title>
  File: <concept_id>
  Issue: <one-sentence description>
  Suggested fix: <concrete action>
```

Return the findings; the parent `SKILL.md` owns the severity definitions, the
combined report format, and the follow-up commands.
