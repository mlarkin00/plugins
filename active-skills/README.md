# active-skills

A curated set of agent skills, installable as a plugin in both Claude Code and Antigravity. This directory is the plugin as it ships in the [`mlarkin00/plugins`](https://github.com/mlarkin00/plugins) marketplace — the one place users install from. The skills under `skills/` are **authored in [`mlarkin00/active-skills`](https://github.com/mlarkin00/active-skills)** and mirrored here by the `sync-active-skills.yml` workflow, so don't edit `skills/` in this repo — the next sync overwrites it.

One directory serves both runtimes: Claude Code reads `.claude-plugin/plugin.json`, Antigravity reads `plugin.json`, and both carry the **same** version as the `marketplace.json` entry.

Everything here is skills or skill-authoring tooling. Usage tracking lives in a separate `skill-usage` plugin, deliberately — keeping telemetry machinery out of the skills keeps them clean.

## Install

**Claude Code** — via the [`mlarkin00-plugins`](https://github.com/mlarkin00/plugins) marketplace:

```
/plugin marketplace add mlarkin00/plugins
/plugin install active-skills@mlarkin00-plugins
```

Skills are namespaced under the plugin, e.g. `active-skills:systematic-debugging`.

**Antigravity** — clone the marketplace repo once, then bulk-install from it:

```bash
git clone https://github.com/mlarkin00/plugins
agy plugin install ./plugins
```

Pointing `agy plugin install` at a directory holding several plugins reports `Found bulk plugins directory` and installs them all, this one included. Antigravity reads Claude-format plugins natively, so one clone covers every plugin in the marketplace.

## How skills get here

Skills are authored in [`mlarkin00/active-skills`](https://github.com/mlarkin00/active-skills), not here. Each is a directory under `skills/` containing a `SKILL.md`, and `skills/` must contain **nothing but skill directories** — Antigravity installs every entry there as a skill, so a loose file becomes a phantom skill in its UI.

A push to the authoring repo dispatches the `sync-active-skills.yml` workflow in this repo. It rsyncs the skills into `skills/`, regenerates the inventory below, and patch-bumps the version. To regenerate the inventory by hand after editing this file:

```bash
bash scripts/gen-readme.sh
```

## Versioning

The plugin carries **one** version, identical in all three places: `.claude-plugin/plugin.json`, `plugin.json`, and the `active-skills` entry in the marketplace's `.claude-plugin/marketplace.json`. Caches are version-keyed, so an unbumped change is never delivered.

`sync-active-skills.yml` bumps all three automatically — but **only when its own run dirties something** (a mirrored skill change). A hand edit to anything outside `skills/` (the `scripts/`, `hooks.json`, `tests/`, or either manifest) is invisible to the sync, so bump all three by hand in the same commit. `active-skills` is deliberately **not** in `release.yml`; the sync owns it alone.

## Layout

| Path | Purpose |
|---|---|
| `skills/` | The skills. Only skill directories belong here. |
| `scripts/gen-readme.sh` | Regenerates the inventory below. |
| `scripts/check_updates.py` | Compares the installed version against the marketplace repo. |
| `scripts/agy_check_updates.py` | Antigravity `Stop` hook: runs the check at most once every 6 hours. |
| `hooks.json` | Antigravity hook declarations. |
| `tests/` | Tests for the update check and its hook gate. |
| `.claude-plugin/plugin.json`, `plugin.json` | The two runtime manifests. |

## Skills

<!-- SKILLS:START -->
**14 skills** (auto-generated — do not edit by hand):

- **`close-session`** — Use when the user says "close session", "wrap up", "end session", "done for now", "save my work", "commit and push", or when finishing a block of work with no further tasks planned to update project documentation, commit changes, and push safely to GitHub.
- **`cloud-build-triggers`** — Use when creating, updating, or managing Google Cloud Build triggers. This skill handles 1st Gen and 2nd Gen GitHub connections, branch patterns, and mandatory IAM validation.
- **`documentation-lookup`** — Use up-to-date library and framework docs via Context7 MCP instead of training data. Activates for setup questions, API references, code examples, or when the user names a framework (e.g. React, Next.js, Prisma).
- **`gcloud`** — Use this skill when interacting with Google Cloud services using the gcloud CLI. Use when managing cloud resources, querying configurations, or troubleshooting issues via gcloud.
- **`git-sync`** — Use this skill when the user asks to sync, update, pull, push, fetch, merge, or rebase the codebase with the remote GitHub repository, or when they run the slash command /git-sync with optional parameters (e.g., "/git-sync", "/git-sync prefer remote", "/git-sync prefer local"). This skill handles git merge or rebase operations safely, ensuring local changes are preserved and prompting the user only if there are irreconcilable merge conflicts, or automatically resolving conflicts if a preference (local/remote) is specified. Make sure to use this skill whenever the user mentions git, remote, syncing, pushing, pulling, or keeping the workspace up to date.
- **`grilling`** — Grill the user relentlessly about a plan or design. Use when the user wants to stress-test a plan before building, or uses any 'grill' trigger phrases.
- **`guidelines`** — Behavioral guidelines to reduce common LLM coding mistakes. Use when writing, reviewing, or refactoring code to avoid overcomplication, make surgical changes, surface assumptions, and define verifiable success criteria.
- **`managing-agent-instructions`** — Use when the user asks to "write a doc", "create agent instructions", "update AGENTS.md", "sync context files", "refine project rules", "update the TODO", "add a task to the backlog", "update DESIGN.md", or "record a lesson learned". Use this skill to manage persistent, high-signal project-specific context in AGENTS.md, GEMINI.md, CLAUDE.md, the project task backlog in .agents/TODO.md, the design system specification in DESIGN.md, and the runtime-evidence knowledge bundle in .agents/wiki/.
- **`new-prompt`** — Pre-processes raw user input through the TCREI framework before execution. Trigger when the user invokes /new-prompt "<task>" or says "refine this prompt then run it". Takes raw intent, applies Task/Context/References structure via the prompt-design skill to produce a constraint-bearing prompt, then executes it as the main task and checks the result against its own constraints.
- **`project-setup`** — Use this skill whenever the current directory lacks an `AGENTS.md` file, a `.git` repository, or other standard project descriptors, indicating it may be a new or unconfigured project. This skill MUST trigger when the user says "set up a new project," "initialize this folder," "start a new repo," or whenever an agent session begins in a directory that doesn't have a clear project-root defined. Proactively use this skill to establish the current directory as the project-root and coordinate the generation of foundational docs via the `managing-agent-instructions` skill.
- **`prompt-design`** — Use this skill whenever the user wants a prompt built, improved, or iterated on — writing a prompt for another AI, refining a system prompt, turning a rough request into something a model will follow, or debugging a prompt that keeps producing the wrong output. Applies the TCREI framework (Task, Context, References, Evaluate, Iterate) to turn vague intent into a deterministic, copy-pasteable prompt. Use it even when the user just describes what they want an AI to do and does not say the word "prompt.
- **`show-context`** — Use this skill whenever the user wants to see or verify what is actually in the session's context window — the user-/project-specific parts. Triggers on /show-context, \"what's in your context\", \"show me your context\", \"dump the context\", \"what context do you have loaded\", \"are my memories being injected\", \"did CLAUDE.md load\", \"is AGENTS.md in context\", \"what did the SessionStart hook add\", \"which skills are loaded\", \"what did that hook inject\", \"confirm X is in context\", or any question about whether a memory, instruction file, hook output, skill listing, or MCP block actually reached the model. Make sure to use this skill even when the user asks casually or about only one piece of context (\"did my memory load?\") — the answer must come from the session transcript, never from introspection or guesswork.
- **`skill-creator-enhanced`** — Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, update or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
- **`skill-improvement`** — Use when reviewing, auditing, critiquing, or improving an EXISTING agent skill against the Agent Skills specification and best practices, and then implementing the fixes — e.g. "audit the skill in active-skills/gcloud against the spec", "review my SKILL.md and make it better", "is this skill following best practices", "improve this skill's triggering", "check my skill for security issues", or a final pass before publishing/sharing a skill. This skill diagnoses a skill (SKILL.md plus its scripts/references/assets) across triggering, progressive-disclosure structure, content quality, path integrity, script safety, security, scoping, and freshness, THEN implements the improvements and re-verifies them. Make sure to use this skill whenever the user wants an existing skill evaluated or upgraded, even if they don't say the word "audit". For authoring a brand-new skill from scratch or running full eval-loop benchmarks, use skill-creator-enhanced instead.
<!-- SKILLS:END -->
