---
type: Pitfall
title: A plugin's SessionEnd hook timeout does not raise the cancellation deadline
description: Claude Code gives the whole SessionEnd batch 1.5s and computes that budget
  only from hooks declared in settings.json, so a plugin hook declaring a 20-second
  timeout is killed mid-work, and the Hook cancelled it reports means aborted rather
  than timed out.
tags:
- claude-code
- hooks
- silent-failure
timestamp: '2026-08-03T17:40:00+00:00'
---

Verified against **Claude Code 2.1.220**.

The symptom is a line on stderr as the session exits:

```
SessionEnd hook [python3 "$CLAUDE_PLUGIN_ROOT/scripts/sync-usage.py" 2>/dev/null || true] failed: Hook cancelled
```

Note what the command cannot do: `2>/dev/null || true` means a failing script still
exits 0. The message is never the hook's own failure.

## "Hook cancelled" means aborted, not timed out

In the 2.1.220 bundle that string is produced in exactly one branch of the hook
spawner — the one taken when the spawn rejects with `ABORT_ERR`. A hook that
outruns its own per-process kill timer reports `Command timed out after …`
instead. So the message always means an `AbortSignal` fired, and the declared
`timeout` is not what fired it.

## The deadline is 1.5s unless settings.json says otherwise

The SessionEnd runner passes `AbortSignal.timeout(…)` over the whole batch,
computed by (de-minified; the identifiers are mangled in the bundle):

```js
let e = env.CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS;
if (e !== undefined && e > 0) return e;
let t = 0, n = [...settingsHooks()?.SessionEnd ?? [], ...managedHooks()?.SessionEnd ?? []];
for (let o of n)
  for (let i of o.hooks)
    if (i.timeout && i.timeout * 1000 > t) t = i.timeout * 1000;
return Math.max(1500, Math.min(t, 60000));   // 1500 = SESSION_END_HOOK_TIMEOUT_MS_DEFAULT
```

That loop walks the settings-file hook config and the managed/policy one. It
never consults the accessor that returns **plugin**-contributed hooks — the
entries carrying `pluginRoot`/`pluginId`, which the `WorktreeCreate` and
`WorktreeRemove` predicates in the same bundle read as a distinct third source.

So on a machine whose `settings.json` files declare no SessionEnd hook, `t`
stays `0` and the deadline floors at **1500 ms**, no matter what a plugin
declares. The declared `timeout` is not entirely inert — it still sets the
per-process kill timer — it just never gets to matter, because the abort fires
first.

## How it was established

The machine had no SessionEnd hook in user, user-local, or project-local
settings; the only one was `skill-usage`'s, declaring `timeout: 20`. Measured
against its real repo, that hook needs **1.0–1.4s**: ~0.03s interpreter start
and import, ~0.1–0.2s for `rev-parse`/`status`/`add`/`commit`, and ~0.9s for
`git push` — a network round trip. That straddles 1500 ms, which is why it
failed intermittently rather than every session.

The residue in the repo pinned the moment of death. The counts commit was
authored at 15:57:22 and the throttle stamp written the same second, yet
`git log @{u}..HEAD` showed the commit as unpushed while `git push --dry-run`
reported `Everything up-to-date` — and `git ls-remote` confirmed the remote
`refs/heads/main` already carried it. The worker was killed after GitHub
accepted the ref update and before git finished updating the local
remote-tracking ref. A kill at ~1s, against a declared 20s: only the 1500 ms
budget explains it.

## The kill is a process-group kill

Two companion facts, both load-bearing for any fix:

* Cancellation sends SIGTERM to the hook's pid, then SIGKILL to the **whole
  process group** 1500 ms later. Hooks are spawned `detached: true`, so the hook
  is its own group leader and a worker merely put in the background stays in that
  group and dies with it. The worker must leave — `setsid`, or Python's
  `start_new_session=True`.
* The runner waits on the hook's stdout and stderr closing, not just on exit. A
  worker inheriting those pipes keeps the session waiting exactly as long as
  doing the work inline did, even after the parent returns. Its stdio has to go
  to `/dev/null`.

## Escape hatches, and why neither is the answer

`CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS` is a typed integer env var checked
before anything else in that function, so it overrides the computation outright.
Declaring any SessionEnd hook in `settings.json` with a large `timeout` also
raises the deadline for the whole batch, plugin hooks included.

Both are user-side machine-local configuration. A plugin that needs either is
broken on every fresh install, so neither belongs in a plugin's design.

## What this repo did

`skill-usage/scripts/sync-usage.py` hands the git work to a worker started with
`start_new_session=True` and stdio on `/dev/null`, and returns immediately;
`--foreground` keeps it inline for the tests. Measured by reproducing the
installed hook command inside its own process group and then group-SIGKILLing
it: the hook returned in **4.7 ms**, the remote was still unchanged at kill time,
and the counts commit landed afterwards regardless.

The same shape is required on Antigravity for an unrelated reason — `Stop` fires
every turn and blocks the loop — so one detached-worker design serves both; see
the [hooks contract](../antigravity/hooks-contract.md) and
[the sidecar finding](../antigravity/sidecar-location.md) that moved this work
into `Stop` in the first place.

Method note: the failure was diagnosed by reading the shipped bundle and timing
the real command, not by trusting the error text — the same discipline as
[plugin updates](plugin-updates.md), where a status line reports something
weaker than what it appears to prove.

# Citations

[1] [mlarkin00/plugins](https://github.com/mlarkin00/plugins)
