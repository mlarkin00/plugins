---
type: Pitfall
title: rsync --delete does not delete excluded files
description: rsync exclude rules are two-sided, so an anchored `- /*` both filters
  the transfer and protects matching destination entries from --delete, letting a
  mirror silently grow into a superset of its source.
tags:
- shell
- rsync
- mirroring
timestamp: '2026-08-06T19:58:00+00:00'
---

An rsync filter rule is applied to **both** sides unless a `s` (sender) or `r`
(receiver) modifier restricts it. On the receiving side an exclude acts as a
**protect** rule: `--delete` will not remove a destination entry that the filter
excludes. Only `--delete-excluded` drops that protection.

So an allow-list built as "`+` every wanted entry, then `- /*`" does not
converge on the source. It is one-way: new entries arrive, changed entries
update, but a **deleted entry is protected by the very rule meant to filter it**
— once it loses its `+` rule it falls under `- /*`, which now shields it.

## Observed

`sync-active-skills.yml` mirrors `mlarkin00/active-skills` into
`active-skills/skills/`, generating one `+ /<name>/` rule per source directory
containing a `SKILL.md`, then `- /*`, and running:

```
rsync -a --delete --filter="merge $FILTER" .source/ active-skills/skills/
```

On 2026-08-06 six skills were removed upstream (`d881a18`). The marketplace
mirror held **40** skills against a source of **34**:

```
auto-mode  code-design  frontend-design
gemini-agents-api  google-antigravity-sdk  refresh-skills
```

Every sync run reported `success`; the version step was correctly skipped as
"no changes", because after rsync there genuinely were none. Reduced to a
fixture — two source skills, a destination also holding `removed-skill`:

```
$ rsync -a --delete --filter="merge $FILTER" source/ dest/
$ ls dest
alpha  beta  removed-skill      # ← survived --delete
```

Adding `--delete-excluded` yields `alpha beta`.

## Consequences

The mirror is monotonic, so a removal never reaches installs. Worse, a
removal-only upstream change produces **no diff at all** in the destination, so
the workflow detects no change, cuts no release, and reports success — the
failure is invisible from both the run log and the version number.

## Fix

Use `--delete-excluded` when the filter is an allow-list and the destination is
a pure mirror. This makes any "abort if the allow-list is empty" guard strictly
load-bearing: with the protection gone, a filter of only `- /*` empties the
destination instead of leaving it untouched. Verified — removing that guard
while keeping the flag reduced the fixture mirror to `[]`.

Because the failure is silent, the semantics are now proved on every run against
a fixture by `.agents/scripts/check-sync-mirror.py`, which executes the
workflow's own `run:` block rather than asserting on its text.

Verified with rsync 3.2.7 on Linux, and against
[ls does not honour argument order](ls-argument-order.md) as a sibling class of
trap: a shell tool whose default behaviour is not the one the caller assumed.

# Citations

[1] [rsync man page — FILTER RULES](https://download.samba.org/pub/rsync/rsync.1)
[2] [mlarkin00/plugins](https://github.com/mlarkin00/plugins)
[3] [mlarkin00/active-skills@d881a18](https://github.com/mlarkin00/active-skills)
