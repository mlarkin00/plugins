# Convention

* [How a skill locates its plugin's scripts](script-resolution.md) - Try three known roots in order as two plain commands; never $CLAUDE_PLUGIN_ROOT, never ls piped to head, never a single substitution line.

# Pitfall

* [Hook output protocols differ between runtimes](hook-output-protocols.md) - Claude Code injects via plain stdout or hookSpecificOutput.additionalContext, Antigravity via injectSteps[].ephemeralMessage; emitting the wrong shape exits 0 and injects nothing.
* [Hook payload keys differ in case between runtimes](payload-key-casing.md) - Claude Code sends snake_case, Antigravity sends protojson camelCase; a shared hook script must read both or it silently no-ops on one runtime.

# Runtime Behaviour

* [Each runtime reads a different briefing file, and only one expands imports](briefing-file-loading.md) - Claude Code loads CLAUDE.md and expands `@` imports but never reads AGENTS.md; agy loads AGENTS.md/GEMINI.md but ignores imports — so no single line reaches both.
* [The Agent Engine has a native Session Service for conversation transcripts](agent-engine-session-service.md) - POST .../reasoningEngines/{id}/sessions + :appendEvent stores ordered SessionEvent records — distinct from the Memory Bank memories endpoint, which stores short extracted facts.
