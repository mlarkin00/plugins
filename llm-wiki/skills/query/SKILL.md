---
name: query
description: Use when the user invokes /llm-wiki:query or asks a question to be answered from an OKF bundle. Reads the index, drills into the relevant concept docs, synthesizes a cited answer, and offers to file it back as a new concept so explorations compound. Also covers finding authoritative sources when the bundle cannot answer.
---

# /llm-wiki:query — Query the Bundle

Karpathy's "Query" operation: read the wiki, synthesize a cited answer,
optionally file it back.

## Usage

```
/llm-wiki:query <question>
/llm-wiki:query  # interactive: prompt for question
```

## Workflow

```
1. Read bundle root's index.md to understand the concept landscape
2. Identify the most relevant concepts by type / title / description
3. Read those concept docs in full
4. Follow relevant cross-links (one hop) if needed for context
5. Synthesize a cited answer
6. Offer to file the answer back as a new concept
```

## Reading the bundle

Start with the root `index.md` — it groups concepts by type and links to every concept. Use `okf_search.py` for keyword lookup:

```bash
python3 <plugin_root>/scripts/okf_search.py <bundle_root> "<keywords>" --k 10
```

For complex questions, read the `CLAUDE.md` at the bundle root first — it explains the bundle's domain, type vocabulary, and conventions.

## Synthesizing the answer

- Be concrete. Quote field names, enum values, SQL snippets from the wiki rather than paraphrasing them.
- **Cite every factual claim** by linking to the concept doc it came from.
- Format: prose answer, then a `## Sources` section listing the concept IDs read.

## Filing the answer back

After answering, offer:

> "Would you like me to file this answer as a concept doc in the bundle? It would be saved as `concepts/<slug>.md` with `type: Q&A` (or whatever type fits your vocabulary) so future queries can find it."

If the owner says yes:
1. Pick a concept ID that fits the bundle structure (follow the `CLAUDE.md` conventions).
2. Write the concept doc by following `authoring-concepts` → `okf_doc.py write`.
3. Cross-link from relevant existing concepts where natural.
4. Suggest `/llm-wiki:index` and `/llm-wiki:log`.

This is the core of the compounding wiki pattern: every answered question makes the wiki more complete.

## If the bundle can't answer

1. Say so clearly — never fill the gap from training data and present it as a bundle answer.
2. Find what would fill it: follow **`references/finding-sources.md`** to recommend authoritative URLs or datasets, each ending in a ready-to-run `/llm-wiki:ingest` command.
3. Offer to seed a stub concept doc to track the gap: `concepts/open-question-<slug>.md` with `type: Open Question`.

## Example

User: "How does the events_ table relate to users?"

Steps:
1. Read `index.md` → identify `tables/events_` and `tables/users`.
2. Read both concept docs.
3. Check `references/joins/` for any join reference.
4. Synthesize: "The `events_` table links to `users` via `user_pseudo_id` — see `references/joins/events___users.md` for the canonical ON clause."
5. Offer to file `concepts/events-users-relationship.md`.

More invocations:

```
/llm-wiki:query "What is the grain of the events_ table?"
/llm-wiki:query "How do I calculate daily active users from this dataset?"
/llm-wiki:query "Which tables contain user_pseudo_id?"
```
