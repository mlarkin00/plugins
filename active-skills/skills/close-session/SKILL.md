---
name: close-session
description: Use when the user says "close session", "wrap up", "end session", "done for now", "save my work", "commit and push", or when finishing a block of work with no further tasks planned to update project documentation, commit changes, and push safely to GitHub.
category: git
---

# Close Session

End-of-session ritual: update docs → commit → classify changes → merge related branches to main → push or hold.

**Core principle:** Every session ends with accurate documentation and a clean, safe git state. Breaking changes MUST NEVER push until the related work is complete — or the user explicitly overrides.

**Announce at start:** "I'm using the close-session skill to wrap up this session."

## Step 1: Update Project Documentation

Invoke the `managing-agent-instructions` skill to update all project documentation.

Focus on changes this session introduced:

- New or changed commands → update `AGENTS.md` / `GEMINI.md` / `CLAUDE.md`
- Architecture shifts → update `ARCH.md`
- New conventions established → update `AGENTS.md`
- Follow-up tasks discovered → add to `.agents/TODO.md` (with `[P1]` or `[P2]`)
- Completed tasks → prune from `.agents/TODO.md`
- **Durable lessons learned → mint a concept in `.agents/wiki/`, not a TODO item** (see below)
- UI tokens or component changes → update `DESIGN.md` and run `npx @google/design.md lint DESIGN.md` (the file argument is required)

If the session made no architectural or convention changes, a brief read-and-confirm that existing docs are still accurate is sufficient — do not update for its own sake.

### Lessons learned vs. follow-up tasks

A **follow-up task** is work still to do → `.agents/TODO.md`. A **lesson learned** is a finding that cost investigation to establish and is not derivable from the code → a concept in `.agents/wiki/`, version-pinned to what it was verified against.

The trap this exists to prevent: a completed TODO carries the resolution note that explains *why* the fix was what it was, and pruning the task in Step 1 deletes that evidence. Before pruning any completed item, ask whether its resolution passes the scope test — if so, mint the concept **first**, then prune.

If the project has no bundle, scaffold one — `/llm-wiki:init .agents/wiki` also wires discovery into the briefing files, which is per-file and not a single line everywhere (bare `@.agents/wiki/index.md` in a standalone `CLAUDE.md`; the catalog **inlined** in `AGENTS.md`/`GEMINI.md`, which `agy` reads but never imports from). After adding concepts, regenerate and validate (`/llm-wiki:index`, `/llm-wiki:validate`) so the index committed in Step 4 is current — `index` also re-syncs the inlined copies, which go stale silently. Full model: `managing-agent-instructions` Phase 6.

## Step 2: Stage and Review Changes

```bash
git status
git diff --stat HEAD
```

Identify two categories:

- **Documentation changes** — `AGENTS.md`, `CLAUDE.md`, `README`, `TODO`, etc.
- **Code/config changes** — implementation, schemas, scripts, config files

If the working tree is already clean (nothing to stage), skip to Step 5 — report clean state and stop.

## Step 3: Classify for Breaking Changes

Scan `git diff HEAD` (or the range of unpushed commits if commits already exist) for these signals:

**Breaking — hold the push:**

- Removed or renamed public functions, methods, or exports
- Changed function signatures (parameters removed, reordered, or types changed incompatibly)
- Removed or renamed CLI commands or flags
- Config format changes that break existing configs (renamed required fields, changed value formats)
- Database migrations that drop columns/tables, or add `NOT NULL` columns without a default
- Changed import paths or module restructuring
- Renamed or removed skill files (for skills repos) or renamed SKILL.md frontmatter fields
- Removed required properties in any public-facing schema

**Not breaking — safe to push:**

- New functions, exports, or CLI commands (additive)
- Bug fixes that don't change the public interface
- New optional config fields
- Documentation-only changes
- New skill files added to a skills repo
- Refactoring with identical external interface
- Test additions or changes

When ambiguous, classify as **breaking** and note why. A conservative hold is recoverable; an accidental push of broken interfaces is not.

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

Once changes are committed and classified as **not breaking**, integrate this session's work into `main`.

Identify the branches related to this session:

- The current working branch, if it is not `main`
- Any feature branches created during the session for this work

If the current branch _is_ `main` and no other session branches exist, skip to Step 6.

**If breaking changes were detected in Step 3, do NOT merge.** Leave the work on its branch and go to Step 6 (hold) — merging breaking changes into `main` defeats the purpose of the hold.

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

### No breaking changes detected

Push `main` (now holding the merged work):

```bash
git push
```

Report: "Session closed. Related branches merged to main and pushed to GitHub."

### Breaking changes detected

**Do NOT merge to `main` and do NOT push.** Leave the work on its branch.

Add a `[P0]` item to `.agents/TODO.md`:

```markdown
- [ ] **[P0]** Push breaking changes from session YYYY-MM-DD — [what is breaking and what work must complete first]
```

Commit this TODO update if not already included, then report:

```
Session closed locally on branch <branch>. NOT merged to main, NOT pushed.

Breaking changes detected:
  - [specific change 1]
  - [specific change 2]

Added [P0] to .agents/TODO.md.
Merge to main and push when:
  1. All related work is complete, OR
  2. You say "push anyway"
```

### User override

If the user explicitly says "push anyway", "force push", or similar — merge the related branches to `main` (Step 5) and push immediately without further checks. Record nothing in TODO.

## Gotchas & Anti-Patterns

| Excuse                                                       | Reality                                                                                               |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| "Small change, probably not breaking"                        | Impact is what matters, not size. Rename a single export and every caller breaks. Classify by effect. |
| "The breaking change is intentional, so it's fine"           | Intent doesn't unbreak callers. Hold until downstream work lands.                                     |
| "I'll push the docs update even if the code is breaking"     | All staged changes travel in the same push. Hold everything or push everything.                       |
| "Nothing to commit, nothing to do"                           | If the session established new conventions, docs need updating even without code changes.             |
| "I already know what the docs say"                           | The session may have shifted implicit conventions. Read before declaring docs current.                |
| "I'll skip managing-agent-instructions — the docs look fine" | "Looks fine" from memory is not the same as confirming currency. Invoke the skill.                    |
| "The task is done, so I'll just delete it from TODO.md"      | A completed item's resolution note is often the only record of *why*. Mint the concept in `.agents/wiki/` first, then prune. |
| "I'll write the lesson as a TODO so it's not lost"           | TODOs are work to do; a closed finding sits there forever looking actionable. Lessons are evidence — they belong in the bundle. |

## Quick Reference

| Scenario                   | Action                                                            |
| -------------------------- | ----------------------------------------------------------------- |
| Only docs changed          | Update → commit → merge to main → push                            |
| Code changed, not breaking | Update docs → commit → merge to main → push                       |
| Code changed, breaking     | Update docs → commit → add `[P0]` TODO → hold on branch, no merge |
| Nothing to commit          | Confirm docs current → report clean state                         |
| Merge conflict on main     | Stop, report conflicting files, ask the user how to proceed       |
| User says "push anyway"    | Merge to main → push immediately, no TODO needed                  |

## Integration

**Follows:**

- Any session that modifies project files
- `executing-plans` — run after all plan steps complete, before declaring done
- `subagent-driven-development` — run after all tasks complete

**Distinct from `finishing-a-development-branch`:**

- `finishing-a-development-branch` guides the _merge strategy decision_ (merge locally / open PR / discard) when you need to deliberate how completed work should land
- `close-session` handles _session hygiene_ (docs + straightforward merge of related branches to `main` + safe push) at the end of any session, regardless of whether the feature is "done"
- Use `finishing-a-development-branch` first when the integration strategy is non-obvious (e.g. the work should become a PR rather than a direct merge); otherwise `close-session`'s Step 5 merge is sufficient