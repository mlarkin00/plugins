---
name: close-session
description: Use when a work session is ending — updates project documentation, commits, and pushes safely to GitHub. Triggers on "close session", "wrap up", "end session", "done for now", "save my work", "let's commit everything and push", or finishing a block of work with no further tasks planned. Make sure to use this skill whenever a session of real work is ending, even if the user only says they are done. For a bare pull, push, or rebase against the remote with no session to close, use git-sync instead.
metadata:
  category: team-automation
---

# Close Session

End-of-session ritual: triage → update docs → classify → commit → merge related branches to main → push or hold.

**Core principle:** Every session ends with accurate documentation and a clean, safe git state. Two things MUST NEVER push: breaking changes before the related work is complete, and secrets or internal identifiers — the first because callers break, the second because a push to a public repo is permanent. Either hold is lifted only by the user explicitly overriding.

**Announce at start:** "I'm using the close-session skill to wrap up this session."

## Step 1: Triage the Session

Run this first, before anything expensive:

```bash
git fetch --quiet      # know where the remote actually is before deciding anything
git status -sb         # branch, upstream, ahead/behind, and working tree in one shot
git diff --stat HEAD   # what this session touched
```

Route on the result:

| Triage result | Route |
| --- | --- |
| Clean tree, in sync with upstream | Confirm docs are current (Step 2, read-and-confirm mode) → report clean state and stop |
| Clean tree, commits ahead of upstream | Skip to Step 3 — classify the unpushed commits, then merge and push |
| Behind upstream | Reconcile before anything else: `git pull --rebase`. If it conflicts, hand off to `git-sync` and stop |
| Dirty tree | Continue to Step 2, carrying the file list from `git diff --stat` |

Triage costs one round trip and decides whether the rest of the skill runs at all. Step 2 is the expensive step — do not pay for it before knowing there is anything to document. `git fetch` belongs here and not later because the most common close is a session on `main` with no branches, and that path otherwise reaches `git push` having never looked at the remote.

## Step 2: Update Project Documentation

Scope the pass to what Step 1 showed changed:

- **Code, config, schemas, scripts, or new conventions touched** → invoke the `managing-agent-instructions` skill.
- **Docs-only changes, or a clean tree** → read the briefing files and confirm they are still accurate. Do not invoke `managing-agent-instructions`; there is nothing for it to reconcile, and it is a multi-phase pass that costs far more than the read.

When it does run, focus on changes this session introduced:

- New or changed commands → update `AGENTS.md` / `GEMINI.md` / `CLAUDE.md`
- Architecture shifts → update `ARCH.md`
- New conventions established → update `AGENTS.md`
- Follow-up tasks discovered → add to `.agents/TODO.md` (with `[P1]` or `[P2]`)
- Completed tasks → prune from `.agents/TODO.md`
- **Durable lessons learned → mint a concept in `.agents/wiki/`, not a TODO item** (see below)
- UI tokens or component changes → update `DESIGN.md` and run `npx @google/design.md lint DESIGN.md` (the file argument is required)

### Lessons learned vs. follow-up tasks

A **follow-up task** is work still to do → `.agents/TODO.md`. A **lesson learned** is a finding that cost investigation to establish and is not derivable from the code → a concept in `.agents/wiki/`, version-pinned to what it was verified against.

The trap this exists to prevent: a completed TODO carries the resolution note that explains *why* the fix was what it was, and pruning the task deletes that evidence. Before pruning any completed item, ask whether its resolution passes the scope test — if so, mint the concept **first**, then prune.

If the project has no bundle, **say so and offer it as a follow-up — do not scaffold one mid-close.** `/llm-wiki:init` creates a directory tree and rewrites all three briefing files to wire discovery, which is more than a session close should do unprompted, and it fails outright if the `llm-wiki` plugin isn't installed.

When a bundle does exist, regenerate and validate after adding concepts (`/llm-wiki:index`, `/llm-wiki:validate`) so the index committed in Step 4 is current — `index` also re-syncs the catalog inlined in `AGENTS.md`/`GEMINI.md`, which goes stale silently because `agy` reads those files but never expands an `@` import. Full model: `managing-agent-instructions` Phase 6.

Note that this doc pass usually dirties the tree. Re-check `git status` before Step 4 so the doc edits are staged with everything else.

## Step 3: Classify — Breaking Changes and Leaks

Read the change once and check it against both hold conditions:

```bash
git diff HEAD          # uncommitted work
git log -p @{u}..      # or, when the commits already exist
```

### Breaking changes — hold the push

- Removed or renamed public functions, methods, or exports
- Changed function signatures (parameters removed, reordered, or types changed incompatibly)
- Removed or renamed CLI commands or flags
- Config format changes that break existing configs (renamed required fields, changed value formats)
- Database migrations that drop columns/tables, or add `NOT NULL` columns without a default
- Changed import paths or module restructuring
- Renamed or removed skill files (for skills repos) or renamed SKILL.md frontmatter fields
- Removed required properties in any public-facing schema

**Not breaking — safe to push:** new functions, exports, or CLI commands (additive); bug fixes that leave the public interface intact; new optional config fields; documentation-only changes; new skill files added to a skills repo; refactoring with an identical external interface; test additions or changes.

When ambiguous, classify as **breaking** and note why. A conservative hold is recoverable; an accidental push of broken interfaces is not.

### Leaks — hold the push

- **Credential shapes** — API keys, tokens, `BEGIN ... PRIVATE KEY` headers, `.env` contents, connection strings carrying a password
- **Internal-only paths and identifiers** — `google3`, `blaze`, `/google/bin`, `go/` shortlinks, internal proto paths
- **Unreleased product or service names written as prose** — a path scan cannot catch these, because they read as ordinary product names. Verify names against public docs before pushing a research doc or anything distilled from one

This outranks every other check: a broken interface is fixed by the next commit, but a leak is in the history permanently, and in a public repo it is world-readable the moment the push lands. Reverting the commit does not remove it.

## Step 4: Commit

Stage all changes and commit:

```bash
git add <specific files>  # prefer explicit over git add -A
git commit -m "<message>"
```

Commit message convention:

- `feat:` new capability
- `fix:` bug fix
- `docs:` documentation only
- `refactor:` restructure, no behavior change
- `chore:` maintenance
- Include `BREAKING CHANGE: <description>` in the commit footer when applicable

If commits already exist but are unpushed, skip the commit step — just classify and push or hold.

## Step 5: Merge Related Branches to Main

Once changes are committed and classified as **not breaking and not leaking**, integrate this session's work into `main`.

Identify the branches related to this session: the current working branch if it is not `main`, plus any feature branches created during the session for this work. If the current branch _is_ `main` and no other session branches exist, skip to Step 6.

**If Step 3 flagged anything, do NOT merge.** Leave the work on its branch and go to Step 6 (hold) — merging into `main` defeats the purpose of the hold.

For each related branch:

```bash
git checkout main
git pull --ff-only            # sync main before merging
git merge --no-ff <branch>    # bring the session branch into main
```

- If the merge produces conflicts, **stop** — do not force. Report the conflicting files and ask the user how to proceed.
- After a clean merge, delete the branch only if it was created for this session and the user hasn't asked to keep it: `git branch -d <branch>`.

When it is unclear which branches belong to this session, **ask the user** rather than merging everything.

## Step 6: Push or Hold

### Nothing flagged in Step 3

Push `main` (now holding the merged work):

```bash
git push
```

If the push is rejected, the remote moved after Step 1's fetch — usually another machine committing to the same repo. Run `git pull --rebase` and push once more. If the rebase conflicts, **stop and hand off to `git-sync`**; never resolve a rejection by force-pushing, which discards whatever landed on the remote.

Report: "Session closed. Related branches merged to main and pushed to GitHub."

### Breaking change or leak detected

**Do NOT merge to `main` and do NOT push.** Leave the work on its branch.

Add a `[P0]` item to `.agents/TODO.md`:

```markdown
- [ ] **[P0]** Push held changes from session YYYY-MM-DD — [what is breaking or leaking, and what must happen first]
```

Commit this TODO update if not already included, then report:

```
Session closed locally on branch <branch>. NOT merged to main, NOT pushed.

Held because:
  - [specific change 1]
  - [specific change 2]

Added [P0] to .agents/TODO.md.
Merge to main and push when:
  1. All related work is complete (or the leak is removed from the change), OR
  2. You say "push anyway"
```

A leak hold has one extra requirement: removing the offending line is not enough if it was already committed locally. The commit must be amended or the history rewritten before the push, or the secret ships anyway.

### User override

If the user explicitly says "push anyway", "force push", or similar — merge the related branches to `main` (Step 5) and push immediately without further checks. Record nothing in TODO.

## Gotchas & Anti-Patterns

| Excuse                                                       | Reality                                                                                               |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| "I'll update the docs first, then check git"                 | The doc pass is the expensive step and triage is one round trip. A clean, in-sync tree ends the session before Step 2 ever loads. |
| "I'm on `main`, so there's nothing to pull"                  | `main` is exactly where an unfetched push rejects — other machines and automation commit here too. Fetch in Step 1, always. |
| "The push was rejected, I'll just force it"                  | A rejection means someone else's work is on the remote. Rebase and retry once; if that conflicts, stop and use `git-sync`. |
| "Small change, probably not breaking"                        | Impact is what matters, not size. Rename a single export and every caller breaks. Classify by effect. |
| "The breaking change is intentional, so it's fine"           | Intent doesn't unbreak callers. Hold until downstream work lands.                                     |
| "No secrets in this diff, it's just docs"                    | Prose leaks too — an unreleased service name in a research doc reads like an ordinary product name and no path scan catches it. Read the prose. |
| "I removed the secret, so it's safe to push"                 | If it was already committed locally, the secret is in the history. Amend or rewrite before pushing.   |
| "I'll push the docs update even if the code is breaking"     | All staged changes travel in the same push. Hold everything or push everything.                       |
| "Nothing to commit, nothing to do"                           | If the session established new conventions, docs need updating even without code changes — that is why Step 2 still runs in read-and-confirm mode on a clean tree. |
| "I already know what the docs say"                           | The session may have shifted implicit conventions. Read before declaring docs current.                |
| "The task is done, so I'll just delete it from TODO.md"      | A completed item's resolution note is often the only record of *why*. Mint the concept in `.agents/wiki/` first, then prune. |
| "I'll write the lesson as a TODO so it's not lost"           | TODOs are work to do; a closed finding sits there forever looking actionable. Lessons are evidence — they belong in the bundle. |

## Integration

**Follows:**

- Any session that modifies project files — this runs last, after the work itself is finished, regardless of whether the feature is "done"

**Invokes:**

- `managing-agent-instructions` (Step 2, conditionally) — updates the briefing files, `.agents/TODO.md`, `DESIGN.md`, and the `.agents/wiki/` bundle
- `git-sync` (Steps 1 and 6) — when reconciling with the remote conflicts

**Scope boundary:** this skill handles _session hygiene_ — docs, commit, a straightforward merge of this session's branches to `main`, and a safe push. It does not deliberate _integration strategy_. When how the work should land is an actual decision (open a PR instead of merging, stack it on another branch, discard it), Step 5 stops and asks rather than merging by default.
