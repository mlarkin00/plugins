---
type: Runtime Behaviour
title: Skill support files ship intact under agy
description: references/ and other files beside a SKILL.md are copied into the install
  tree at the same relative paths, so progressive disclosure works on both runtimes.
tags:
- antigravity
- install
- skills
timestamp: '2026-08-13T19:55:02+00:00'
---

A skill is installed as a **directory**, not as a single `SKILL.md`, so
`references/`, `templates/`, `scripts/` and `assets/` beside it are copied into
the install tree at the same relative paths. Progressive disclosure therefore
works on both runtimes: detail can live in a support file the model reads only
when it takes that path, instead of in a sibling skill whose description is
loaded on every turn.

Verified 2026-08-13 on **agy 1.1.12**. A bulk `HOME=$(mktemp -d) agy plugin
install "$PWD"` of this marketplace put 25 `references/*.md` on disk under
`~/.gemini/config/plugins/<plugin>/skills/<skill>/references/`, and after
`llm-wiki` was consolidated from 18 skills to 9 the same install landed all 9
skill directories with their 6 reference files intact. Claude Code needed no
check — 11 `active-skills` skills have shipped this shape there for months.

## What this does and does not establish

It establishes the **plumbing**: the files exist, at the path a SKILL.md's
relative link resolves against. Per [installer counts are not
evidence](installer-counts.md) the check was a directory listing of the install
tree, not the installer's own component counts.

It does not establish that a live `agy` session *follows* the pointer — that is
ordinary model behaviour, identical on both runtimes, and not a runtime property.
The failure mode worth guarding against was the runtime one: a plugin that
demoted its detail to `references/` and then shipped skills whose instructions
pointed at files that were never copied.

## Consequence

Prefer a `references/` file over a second skill whenever content is
source-specific, deep, or only needed on one branch of a workflow. Every skill
description is loaded into every session, so a sibling skill is the most
expensive way to store a paragraph — and unlike [agents](component-support.md),
support files carry no runtime asymmetry between Claude Code and Antigravity.

Note that [install is additive](install-is-additive.md): a support file removed
from the source is **not** deleted from an existing install, so a renamed
reference leaves the old copy behind for anything still pointing at it.

# Citations

[1] Bulk install into a throwaway `HOME`, agy 1.1.12, 2026-08-13, this repo.
[2] `mlarkin00/plugins` llm-wiki 18-skill consolidation, same date.
