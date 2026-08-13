# TODO

Defects found in the 2026-07-22 runtime review are tracked in the marketplace
backlog (`.agents/TODO.md` at the repo root) rather than here, because their
root causes are shared with other plugins.

Closed 2026-07-22: the `PostToolUse` validator resolved to an empty path under
Antigravity (P0). This plugin now carries a root `hooks.json` and a root
`plugin.json`; `hooks/validate-on-write.sh` reads both runtimes' payload shapes
and resolves the validator from its own location instead of
`$CLAUDE_PLUGIN_ROOT`, which Antigravity does not define. Also closed: the ten
`commands/*.md` wrappers that shadowed their identically-named skills, deleted in
`f01e7a7` (which took the unparseable `commands/stats.md` frontmatter with them).

Closed 2026-07-22: **discovery** (P1) and the reserved-filename disagreement
between `okf_index.py` and `okf_validate.py` (P2). `scripts/okf_discover.py`
installs and refreshes the mechanism, `/llm-wiki:init` runs it, `/llm-wiki:index`
re-syncs it, `tests/test_okf_discover.py` covers it, and both runtimes were
verified to see the catalog in a live session. The premise the item was written
on turned out to be wrong and is recorded in
`.agents/wiki/cross-runtime/briefing-file-loading.md`: `@` imports are **not**
loaded by both runtimes — Claude Code expands them but never reads `AGENTS.md`,
`agy` reads `AGENTS.md` but never expands them, and a backticked `` `@path` `` is
inert on both. This repo's own bundle was reachable on neither runtime until the
fix landed. Reserved names now live in `okf_lib/paths.RESERVED_FILENAMES`.

## P1 — Important / Unblocking

- [ ] **[P1]** Repoint `/llm-wiki:stats` upstream in `mlarkin00/active-skills`.
      The 2026-08-13 consolidation retired that command; it is now
      `/llm-wiki:lint --quick`. Two files still name it —
      `skills/managing-agent-instructions/SKILL.md` (~L304) and
      `skills/managing-agent-instructions/references/knowledge-bundle.md` (~L186).
      They cannot be fixed here: `active-skills/skills/` is the rsync mirror and
      is overwritten on every sync. Until the upstream PR lands and syncs, an
      agent following `managing-agent-instructions` will type a command that no
      longer exists. `/llm-wiki:validate`, `:index`, `:init` and `:lint` are also
      referenced there and all still resolve.

## P2 — Nice-to-Have

- [ ] **[P2]** Add a sidecar to run periodic/background bundle maintenance — schedule the passes that currently only happen when a human remembers to type them (`/llm-wiki:lint` for semantic drift, `/llm-wiki:log` for dated entries, plus `okf_index.py` / `okf_validate.py` / `okf_stats.py`). Open questions: timer mechanism (systemd timer vs. cron vs. `SessionStart` hook), whether lint's LLM pass runs unattended or only reports, and how findings surface (write to `log.md`, open a report doc, or notify). Prior art: `local-minions`' `minion-memory-sidecar.timer`.
- [ ] **[P2]** Add `raw/` sources layer convention to `/llm-wiki:init` — scaffold a `raw/` subdirectory alongside the bundle and document the convention in `templates/bundle-CLAUDE.md`; currently unspecced (DESIGN.md §13).
- [ ] **[P2]** Implement multi-bundle repo detection — find nearest ancestor directory containing a root `index.md` with `okf_version: "0.1"` instead of requiring an explicit `<bundle_root>` argument (DESIGN.md §13).
- [ ] **[P2]** Add integration smoke test for augmentation guard — create a fixture bundle, write a doc with a known `# Schema` field count, then confirm `okf_doc.py write --web-pass` correctly blocks a shrink attempt.
- [ ] **[P2]** Add `--dry-run` to `okf_doc.py write` — preview what would be written without mutating disk; useful for agent debugging.
- [ ] **[P2]** Add shard-family wildcard display to `okf_bq.py list` output — currently lists every shard individually; collapse `prefix_YYYYMMDD` families to `prefix_*` with a count annotation.
