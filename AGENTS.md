# mlarkin00-plugins Marketplace

## Project Goal

Single install point for one plugin set across **two runtimes** — Claude Code (via the `mlarkin00-plugins` marketplace) and Antigravity (`agy`, via a clone bulk-installed with `agy plugin install <clone>`). Owns their versioning, tagging, and GitHub releases. A change that works on only one runtime is not done.

## Project Context

Each top-level directory is one plugin serving both runtimes from one copy: `.claude-plugin/plugin.json` (Claude) and `plugin.json` (Antigravity) carrying the same version, plus some of `skills/`, `agents/`, `commands/`, `hooks/hooks.json` (Claude), `hooks.json` (Antigravity), `scripts/`. `.claude-plugin/marketplace.json` lists them. No build step; `active-skills`, `llm-wiki`, `memory-bank` and `skill-usage` carry `tests/`, run under stdlib `unittest` (no pytest).

| Plugin | Versioned by |
|---|---|
| `agent-memory`, `llm-wiki`, `memory-bank`, `skill-usage` | `release.yml` (auto) |
| `active-skills` | `sync-active-skills.yml` (auto) |

Per-plugin briefings: `llm-wiki/AGENTS.md`, `memory-bank/AGENTS.md`. Backlog: `.agents/TODO.md`. **Runtime evidence — how each rule below was established, and against which version — is the OKF bundle catalogued at the bottom of this file** (authoring and maintenance: `.agents/wiki/CLAUDE.md`). Open the specific concept before changing a guard. **`CLAUDE.md` is a hand-propagated twin of this file** — Claude Code never reads `AGENTS.md` and `agy` never expands `@` imports, so each runtime gets its own file and its own discovery mode (catalog inlined here, imported there). Any convention edit here MUST be made there too.

## Operational Commands

```bash
# Verify every manifest entry resolves on disk and ALL THREE versions agree
# (marketplace entry, Claude manifest, Antigravity manifest) — run after any plugin change
python3 .agents/scripts/check-manifest-versions.py

# Regenerate the active-skills README inventory (CI runs this after every sync)
bash active-skills/scripts/gen-readme.sh

# Prove the active-skills mirror still propagates upstream DELETIONS. It executes
# the sync workflow's own mirror block against a fixture — run after any edit to
# sync-active-skills.yml (the sync itself runs it before every mirror)
python3 .agents/scripts/check-sync-mirror.py

# Verify the AGENTS.md / CLAUDE.md twins agree outside their two deliberately
# divergent regions — run after ANY convention edit (CI runs it too)
python3 .agents/scripts/check-briefing-twins.py

# Confirm the release workflow names no plugin that has been deleted
grep -n 'PLUGINS=' .github/workflows/release.yml

# Claude: validate a plugin or the marketplace manifest
claude plugin validate <plugin>|.

# Claude: adopt a released fix. The name MUST be qualified (a bare name exits
# "Plugin not found"), restart after, and confirm installed_plugins.json moved —
# `details` shows the newest cached version, not the loaded one.
claude plugin marketplace update mlarkin00-plugins && claude plugin update <plugin>@mlarkin00-plugins

# Antigravity: the ONLY reliable check is a bulk install into a throwaway HOME.
# `agy plugin validate <path>` hard-fails on any plugin lacking a root plugin.json.
HOME=$(mktemp -d) agy plugin install "$PWD"

# Jetski & Antigravity ONLY: install/uninstall the hourly git polling systemd timer.
# Do NOT use with Claude Code or clients that have proper marketplace/plugin install/update.
./.agents/scripts/install-poll-service.sh
./.agents/scripts/uninstall-poll-service.sh

# Tests (stdlib unittest — pytest is not installed). Runs every suite.
for p in active-skills llm-wiki memory-bank skill-usage; do (cd $p && python3 -m unittest discover -s tests -q); done
```

## Style & Conventions

- A plugin's `version` MUST be identical in **all three** places: `.claude-plugin/plugin.json` (Claude), `plugin.json` (Antigravity), and its `marketplace.json` entry. One directory serves both runtimes, so one version describes it. Both workflows write all three; hand edits MUST too. The Antigravity manifest is optional — a plugin without one is fine, and `release.yml` logs a `::notice::` and bumps the Claude manifest alone.
- Adding or removing a plugin means three edits: the directory, the `marketplace.json` entry, and the `PLUGINS` list in `release.yml`. Missing the third leaves a stale name in the loop that drives releases.
- Never bump a version by hand for a plugin in a workflow's `PLUGINS` list — a manual bump races the bot. `active-skills` is the exception in reverse: `sync-active-skills.yml` patch-bumps it (both manifests + `marketplace.json`) on every mirrored skill change, and it is not in `release.yml`.
- **Hand edits to `active-skills/` outside `skills/` need a hand bump.** The sync only bumps when its own run dirties something, so a change you commit to `scripts/`, `hooks.json`, `tests/`, or a manifest is invisible to it and nothing else versions the plugin. Unbumped means never delivered, because caches are version-keyed. Bump both manifests and `marketplace.json` in the same commit.
- Changes that cannot affect an install do not trigger a release: `release.yml` filters `<plugin>/README.md`, `<plugin>/AGENTS.md`, `<plugin>/CLAUDE.md`, `<plugin>/GEMINI.md`, `<plugin>/.github/`, and `<plugin>/.agents/` — all agent-facing repo metadata that no install loads. A release burns a version and invalidates version-keyed caches, so a backlog or briefing edit must not cut one. The filter is anchored to the plugin root, so a nested `skills/<name>/SKILL.md` still releases. Anything else under a plugin directory does.
- **A hook that must run under Antigravity MUST be declared in a hand-written root `hooks.json`.** Shape: `{"<hook-name>": {"<Event>": [...]}}`. `PreToolUse`/`PostToolUse` take a `{matcher, hooks}` wrapper; `PreInvocation`/`PostInvocation`/`Stop` take a flat handler list. Those five are the only events — there is no `SessionStart` and no `SessionEnd`. Commands MUST be relative (`./scripts/x.sh`); cwd is the directory holding `hooks.json`. Copy the working shape from `skill-usage/hooks.json`.
- **`$CLAUDE_PLUGIN_ROOT` is populated for Claude hooks only.** It is empty in any command the model runs, and undefined everywhere in Antigravity. Skills MUST locate a script by trying, in order, `~/.claude/scripts/<plugin>/…`, `~/.gemini/config/plugins/<plugin>/scripts/…`, then `~/.claude/plugins/cache/*/<plugin>/*/scripts/…` — as two plain commands (a lookup, then the call). Never `ls a b c | head -1` (`ls` sorts, so it picks a stale cache copy) and never one `$(…)` line (auto-denied in headless agy). See `@memory-bank/AGENTS.md`.
- Session-once work has no Antigravity equivalent: map it to `PreInvocation` **and gate it**, since that fires before every model call and blocks the loop. Gate on `conversationId`; if the hook injects context, cache and replay the payload rather than skipping, because `ephemeralMessage` is transient.
- **Periodic work must be a gated `Stop` hook — never a sidecar.** The agy CLI starts no sidecar manager, so `sidecars/` is inert wherever it sits, and nothing outside `plugins/<name>/` is created, refreshed, or removed by `agy plugin install`/`uninstall`. `Stop` fires every turn, so gate on a timestamp file and detach the slow part (below).
- **Slow or network work in a hook MUST go to a detached worker.** Claude Code cancels the whole `SessionEnd` batch after 1.5s and computes that budget only from `settings.json` hooks, so a plugin's own `timeout` cannot raise it. The worker MUST start its own session (`setsid`; Python `start_new_session=True`), because the hook's entire process group is signalled, and MUST send stdio to `/dev/null`, because the runner waits for those pipes to close. Reference shape: `skill-usage/scripts/sync-usage.py`; evidence: `@.agents/wiki/claude-code/sessionend-hook-deadline.md`.
- **The hourly git polling systemd service (`mlarkin00-plugins-poll.timer`) must only be used with Jetski and Antigravity.** It must not be used with clients that have proper marketplace/plugin install/update mechanisms (e.g. Claude Code), where marketplace updates are handled natively by the client.

## Architecture & Constraints

**Not every component type works on both runtimes.** Skills and hooks work on both; `agents/` install on Antigravity and are unreachable there; sidecars never run there at all, because the CLI starts no sidecar manager; `commands/` convert only on the claude-format path. Full matrix and the evidence: `@.agents/wiki/antigravity/component-support.md`. Design around it — anything a plugin must *do* on Antigravity has to be a skill or a hook.

**No plugin here ships an `agents/` directory.** As of 2026-07-23 the eight former agents across `agent-memory`, `memory-bank` and `llm-wiki` are skills and scripts — an agent that installs but cannot be invoked is worse than none, because a skill that dispatches it becomes an unfollowable instruction. Parallel fan-out is not a component type; it is a dispatch choice inside a skill (a `general-purpose` subagent per unit on Claude Code, sequential on Antigravity). Keep one procedure per task so the runtimes cannot drift. If you add an agent, it is Claude-only by construction — prefer a skill.

**Two independent release paths.** `release.yml` fires on every push to `main`, patch-bumps any plugin in its `PLUGINS` list with release-relevant changes, commits as `github-actions[bot]`, tags `<plugin>-v<version>`, and cuts a GitHub release. It guards against its own push with `if: github.actor != 'github-actions[bot]'`. `sync-active-skills.yml` is separate and owns `active-skills`.

`active-skills` MUST stay out of `release.yml`. The sync job commits to `main` on its own; a second versioner would let a rebase race onto a competing bump and produce conflicting or duplicate `active-skills-v<N>` tags.

**`active-skills/` is a real plugin; only its `skills/` is a mirror.** The manifests, `scripts/`, `hooks.json`, `tests/`, `README.md`, and `AGENTS.md` are hand-maintained **here** and are yours to edit. `active-skills/skills/` is the rsync target and is overwritten on every sync — change skills in `mlarkin00/active-skills`, never here.

`sync-active-skills.yml` runs on `repository_dispatch`, a daily 06:17 UTC poll, or manual dispatch. It selects by contract — **a skill is a top-level source directory containing a `SKILL.md`** — so the authoring repo can hold `README.md`/`docs/` without shipping phantom skills (Antigravity installs *every* entry under `skills/` as one). Skips are logged as a `::notice::`.

Three guards are load-bearing, not stylistic. The rsync destination is `active-skills/skills/`, so `--delete` cannot reach the plugin's own files one level up; an earlier whole-directory mirror ran against a restructured source, flattened the skills to the plugin root, deleted the manifests and the plugin's own scripts, and **reported success** (`716fb23`, recovered in `0ca72e7`). The run aborts on zero skills, which would otherwise empty the plugin and commit it as a success. And the rsync carries `--delete-excluded`, because rsync exclude rules are two-sided: the anchored `- /*` that filters non-skill entries *also protects* matching destination entries from `--delete`, so a skill deleted upstream kept shipping and the mirror grew into a superset of the source (found 2026-08-06 at 40 skills against 34, every run green). That flag makes the zero-skill abort strictly load-bearing — with the protection gone, a source that reads as empty now wipes the mirror instead of leaving it untouched. Evidence: `@.agents/wiki/testing/rsync-protects-excluded.md`.

**A removal-only upstream change is the sync's blind spot.** Deletions were invisible for weeks because they produce no destination diff — so `Detect changes` saw nothing, no version was bumped, no release was cut, and the run log said `success`. Never read a green sync as proof the mirror matches the source; compare the two directory listings. `check-sync-mirror.py` now proves the semantics against a fixture before every mirror, executing the workflow's own `run:` block rather than asserting on its text.

The vendoring exists because `agy plugin install <clone>` installs every plugin *physically present* — so `active-skills` must be here, not merely referenced. There is no ad-hoc agy install from a repo URL, and `agy plugin import claude` does not work.

**Expect the remote to move under you.** A push to `mlarkin00/active-skills` dispatches here, and the sync bot commits to `main` on its own. A local push racing it gets rejected; rebase, never force.

**Never:**
- Treat `agy plugin install` output as evidence. Its component counts report what the installer walked, not what the runtime can use. Verify by observing an effect: a marker file, a counted skill, a validator line in `~/.gemini/antigravity-cli/cli.log`, a committed memory. Evidence: `@.agents/wiki/antigravity/installer-counts.md`.
- Run `install-symlinks.sh` from the Antigravity copy — it links into `~/.claude/` and would repoint Claude Code's symlinks at the agy install
- Edit anything under `active-skills/skills/` — it is the mirror and is overwritten on the next sync; change skills in `mlarkin00/active-skills`
- Change the source layout `sync-active-skills.yml` reads without fixing the workflow first — that ordering is what caused `716fb23`
- Hand-bump a version for a plugin listed in a workflow's `PLUGINS`
- Leave a deleted plugin's name in `release.yml` — under `set -euo pipefail` a `jq` read of its missing `plugin.json` aborts the release step
- Force-push `main` — the release and sync bots both commit here

<!-- llm-wiki:discovery .agents/wiki START -->

## Knowledge bundle — `.agents/wiki`

Open the concept before re-deriving anything it covers.

### Subdirectories

* [antigravity](.agents/wiki/antigravity/index.md) - Contains 9 entries: Which plugin components actually work on Antigravity, Headless permission matching is first-word based, Antigravity hooks contract, agy plugin install is additive — it never deletes files removed from the source, Two install paths, selected by the root plugin.json, agy plugin install component counts are not evidence, $CLAUDE_PLUGIN_ROOT does not exist in Antigravity, PreInvocation is not SessionStart, The agy CLI never starts the sidecar manager.
* [claude-code](.agents/wiki/claude-code/index.md) - Contains 4 entries: An agent whose frontmatter is not valid YAML is skipped silently, Updating an installed Claude Code plugin, A plugin's SessionEnd hook timeout does not raise the cancellation deadline, Injected context is stored as typed records, not as rendered system-reminder text.
* [cross-runtime](.agents/wiki/cross-runtime/index.md) - Contains 4 entries: Each runtime reads a different briefing file, and only one expands imports, Hook output protocols differ between runtimes, Hook payload keys differ in case between runtimes, How a skill locates its plugin's scripts.
* [testing](.agents/wiki/testing/index.md) - Contains 3 entries: ls does not honour argument order, Popping a patched module makes tests hit the network, rsync --delete does not delete excluded files.

<!-- llm-wiki:discovery .agents/wiki END -->
