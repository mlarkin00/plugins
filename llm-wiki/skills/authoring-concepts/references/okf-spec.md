# OKF v0.1 Spec — Distilled Rules

Source of truth: `GoogleCloudPlatform/knowledge-catalog/okf/SPEC.md`

The full format rules behind every llm-wiki operation. `authoring-concepts`
covers the authoring workflow; this file is the spec it conforms to. Read it when
a question is about the *format* — what a conformant doc must contain, what a
concept ID may look like, which files are reserved, how links and citations are
written.

## What a bundle is

A bundle is a directory tree of UTF-8 markdown files. Every non-reserved `.md` file is a **concept doc**. Consumption is deliberately **permissive** — unknown types, broken links, and missing optional fields must be tolerated.

## Frontmatter

Every non-reserved `.md` file MUST have a `---`-delimited YAML frontmatter block. Only one key is required:

| Key | Required | Notes |
|---|---|---|
| `type` | **YES** | Non-empty string. Any value; OKF is open. Examples: `Article`, `Concept`, `Reference`, `BigQuery Table`. |
| `title` | recommended | Short display name; used verbatim in `index.md`. |
| `description` | recommended | One sentence; used verbatim in `index.md`. Keep tight. |
| `resource` | recommended | URI of the underlying asset (BigQuery REST URI, URL, file path). |
| `tags` | recommended | YAML list of search terms. |
| `timestamp` | recommended | UTC ISO-8601, e.g. `2026-06-19T14:30:00+00:00`. Auto-filled by `okf_doc.py write`. |

**Key order for serialization** (enforced by `okf_doc.py`): `type, resource, title, description, tags, timestamp`, then any extras.

**Serialization**: `yaml.safe_dump(sort_keys=False, allow_unicode=True)`. Body must end with `\n`.

## Concept IDs

A concept ID is the file path minus the `.md` extension, relative to the bundle root. Example: `tables/users.md` → `tables/users`.

Segment regex: `[A-Za-z0-9_][A-Za-z0-9_.\-]*`. Each path segment must match.

## Reserved files

- **`index.md`** — auto-generated catalog (one per directory). No frontmatter, except the bundle root `index.md` which carries `okf_version: "0.1"`. Never write by hand; use `okf_index.py`.
- **`log.md`** — chronological append-only change log. Sections: `## YYYY-MM-DD`, newest first. Use `/llm-wiki:log` to append.

## Cross-links

Plain markdown links between concept docs. Use **file-relative paths** so links work on GitHub and in the visualizer:

```markdown
# From tables/users.md:
[events table](events.md)            # sibling
[dataset](../datasets/my_dataset.md) # parent dir
[metric ref](../references/dau.md)   # sibling dir
```

Rules:
- Never use absolute paths (starting with `/`) — they break GitHub rendering.
- Only link to concept IDs that actually exist.
- One link per concept mention per section is enough; don't over-link.
- Don't link from headers, fenced code blocks, or schema field-name listings.

## Citations

Use numbered reference format in `# Citations` sections:

```markdown
# Citations

[1] [Source Title](https://example.com/...)
[2] [Another Source](https://example.com/...)
```

Only cite URLs you actually fetched or know. Do not invent URLs.

## Conformance (§9)

A conformant bundle: every non-reserved `.md` file has parseable YAML frontmatter with a non-empty `type`. The `okf_validate.py` script and the PostToolUse hook both enforce this. Exit non-zero = violation.

## Bundle root

The root `index.md` carries `okf_version: "0.1"` in its frontmatter — the only index.md that has frontmatter. A directory with this file is the bundle root.

## The `raw/` convention (optional)

Karpathy's three-layer wiki: `raw/` holds immutable source files (PDFs, docs, notes). The LLM reads from `raw/` and writes concept docs into the bundle. Not required by OKF spec; use it when you want clear separation of sources from the synthesized wiki.
