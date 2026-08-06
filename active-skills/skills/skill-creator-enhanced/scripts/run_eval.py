#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether a skill's description causes Claude to trigger the skill for a set
of queries. Outputs results as JSON.

Two modes, because they answer different questions:

  live   Run the query against the installed skill set and count a call to the
         skill under test. Measures the *shipped* description in the competitive
         environment it actually lives in -- which is also the only way to see
         which of several overlapping skills wins a near-miss query.

  probe  Inject a throwaway command file carrying a *candidate* description under
         a unique name and count calls to that name. The only way to measure a
         description that is not installed, e.g. inside an optimization loop.

Probe mode has a failure mode worth understanding: if the skill under test is
ALSO installed (every skill in this repo is, via the marketplace), the installed
copy competes with the probe and usually wins, because it carries a description
the model already matches. Those runs measure nothing about the candidate. They
are counted separately as `contaminated` and reported loudly rather than being
silently scored as misses -- scoring them as misses is what made a working
description read as 0.00 and would send an unattended loop iterating toward
nothing.
"""

import argparse
import atexit
import glob
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from scripts import stats
from scripts.utils import parse_skill_md

# Per-run outcomes.
PROBE = "probe"  # the injected candidate description fired (probe mode only)
SELF = "self"  # the installed skill under test fired
OTHER = "other"  # some other skill fired
NONE = "none"  # no skill fired


# --------------------------------------------------------------------------
# Nested-session lifecycle
#
# Every run spawns a real `claude -p` session that costs money for as long as it
# lives. Those sessions are grandchildren -- parent -> pool worker -> claude --
# and killing the parent does not kill them: pool shutdown lives in the parent's
# atexit, which never runs on a signal, and the workers are separate processes
# that outlive it holding their children. Observed 2026-08-06: SIGKILL to
# run_loop.py left 11 nested sessions running and billing, re-parented away and
# invisible.
#
# So: each session gets its own process group (killing the group reaps whatever
# `claude` itself spawned), the group is registered here, and SIGINT / SIGTERM /
# normal exit all reap the registry. SIGKILL cannot be caught by anyone, so PIDs
# are also appended to a file for `--cleanup` to sweep afterwards.
# --------------------------------------------------------------------------

PIDFILE_ENV = "SKILL_EVAL_PIDFILE"
_ACTIVE_PGIDS: set[int] = set()


def _kill_pgid(pgid: int, grace: float = 0.3) -> None:
    """SIGTERM a process group, then SIGKILL anything that ignored it."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(grace)
        try:
            os.killpg(pgid, 0)  # still there?
        except (ProcessLookupError, PermissionError):
            return


def _reap_all(signum=None, frame=None) -> None:
    for pgid in list(_ACTIVE_PGIDS):
        _kill_pgid(pgid)
    _ACTIVE_PGIDS.clear()
    if signum is not None:
        # Re-raise as a normal exit so the pool unwinds and the parent sees it.
        sys.exit(128 + signum)


def _record_pid(pid: int) -> None:
    """Append a nested session's PID so `--cleanup` can sweep after a SIGKILL."""
    path = os.environ.get(PIDFILE_ENV)
    if not path:
        return
    try:
        with open(path, "a") as fh:
            fh.write(f"{pid}\n")  # single short write; append is atomic enough
    except OSError:
        pass


def install_reaper() -> None:
    """Reap nested sessions on exit and on catchable signals.

    Called at import so it is installed in pool workers too -- they are where the
    sessions actually live, and they are what survives a parent that dies badly.
    """
    atexit.register(_reap_all)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _reap_all)
        except (ValueError, OSError):
            pass  # not the main thread; atexit still covers the normal path


install_reaper()


def _ancestry(pid: int, limit: int = 64) -> set[int]:
    """This process and every parent up to init, so a sweep cannot kill itself."""
    seen: set[int] = set()
    for _ in range(limit):
        if pid <= 1 or pid in seen:
            break
        seen.add(pid)
        try:
            with open(f"/proc/{pid}/stat", "rb") as fh:
                # ppid is field 4, but the comm field can contain spaces or
                # parentheses -- split after the final ')'.
                fields = fh.read().decode("utf-8", "replace").rpartition(")")[2].split()
            pid = int(fields[1])
        except (OSError, IndexError, ValueError):
            break
    return seen


def sweep_orphans(pidfile: str, dry_run: bool = False) -> list[int]:
    """Kill nested sessions recorded in `pidfile` that are still alive.

    The PID is checked against its own command line before anything is signalled
    -- PIDs get recycled, and a stale file must never take out an unrelated
    process that happens to inherit the number.
    """
    killed: list[int] = []
    try:
        pids = [int(line) for line in open(pidfile) if line.strip().isdigit()]
    except OSError:
        return killed

    self_and_ancestors = _ancestry(os.getpid())

    for pid in dict.fromkeys(pids):
        if pid in self_and_ancestors:
            continue  # never signal ourselves or whatever launched us
        try:
            raw = open(f"/proc/{pid}/cmdline", "rb").read()
        except OSError:
            continue  # already gone
        argv = [a for a in raw.decode("utf-8", "replace").split("\0") if a]
        # Substring matching is not good enough here -- this sends SIGKILL, and
        # "claude" appears in ordinary paths (/tmp/claude-.../) while " -p "
        # appears in ordinary commands (`ps -p 123`). A substring guard was
        # observed matching the very shell that invoked the sweep.
        #
        # Requiring argv[0] to be claude is too strict in the other direction:
        # if `claude` is a shebang wrapper the kernel rewrites argv[0] to the
        # interpreter, giving ["/bin/bash", "/path/to/claude", "-p", ...].
        #
        # So: some argument must be *exactly* named claude, and -p must be
        # present as its own argument.
        if not any(Path(a).name == "claude" for a in argv):
            continue
        if "-p" not in argv:
            continue
        killed.append(pid)
        if not dry_run:
            try:
                _kill_pgid(os.getpgid(pid))
            except (ProcessLookupError, PermissionError):
                pass
    return killed


def find_project_root() -> Path:
    """Find the project root by walking up from cwd looking for .claude/.

    Mimics how Claude Code discovers its project root, so the command file
    we create ends up where claude -p will look for it.
    """
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".claude").is_dir():
            return parent
    return current


def find_installed(skill_name: str) -> list[tuple[str, str | None]]:
    """Locate installed copies of `skill_name`, as (path, plugin@marketplace).

    A probe run measures a candidate description by injecting it under a
    throwaway name. If a real copy of the skill is installed it carries the
    *shipped* description, competes for the same call, and usually wins -- so
    those runs measure nothing about the candidate.
    """
    home = Path.home()
    found: list[tuple[str, str | None]] = []

    # User-level: ~/.claude/skills/<name>/SKILL.md -- not a plugin, cannot be
    # disabled by settings; the caller has to move it.
    p = home / ".claude" / "skills" / skill_name / "SKILL.md"
    if p.exists():
        found.append((str(p), None))

    # Plugin cache: .../cache/<marketplace>/<plugin>/<version>/skills/<name>/SKILL.md
    for hit in glob.glob(str(home / ".claude/plugins/cache/*/*/*/skills" / skill_name / "SKILL.md")):
        parts = Path(hit).parts
        found.append((hit, f"{parts[-5]}@{parts[-6]}"))

    # Marketplace checkouts: .../marketplaces/<marketplace>/<plugin>/skills/<name>/SKILL.md
    for hit in glob.glob(str(home / ".claude/plugins/marketplaces/*/*/skills" / skill_name / "SKILL.md")):
        parts = Path(hit).parts
        found.append((hit, f"{parts[-4]}@{parts[-5]}"))

    return found


def plugin_keys_for(skill_name: str) -> list[str]:
    """The `enabledPlugins` keys that would need disabling to isolate a probe."""
    return sorted({key for _, key in find_installed(skill_name) if key})


def isolation_settings(skill_name: str) -> str | None:
    """Inline `--settings` JSON that hides the installed copy from a nested run.

    `--settings` accepts a JSON string and merges over the user's settings for
    that process only, so this isolates the measurement without touching the
    user's environment -- unlike `claude plugin disable`, which is global, is
    visible in their interactive sessions, and has to be remembered and undone.

    Verified 2026-08-06, Claude Code 2.1.x: with this applied, `active-skills`
    entries drop out of the advertised skill list entirely and a query that
    otherwise fires `active-skills:prompt-design` fires nothing.

    Caveat: the unit is the plugin, not the skill, so sibling skills in the same
    plugin disappear too. For measuring *positives* that is fine. For measuring
    over-triggering against those siblings it is not -- use live mode there.
    """
    keys = plugin_keys_for(skill_name)
    if not keys:
        return None
    return json.dumps({"enabledPlugins": {k: False for k in keys}})


def matches_skill(fired: str, skill_name: str) -> bool:
    """Whether a fired skill name refers to the skill under test.

    Claude reports plugin skills plugin-qualified (`active-skills:prompt-design`)
    and local ones bare (`prompt-design`), so match either form. Substring
    matching is deliberately avoided: `prompt-design` is a substring of
    `prompt-design-v2`.
    """
    if not fired:
        return False
    return fired == skill_name or fired.endswith(f":{skill_name}")


def _skill_from_json(accumulated: str) -> str:
    """Pull the `skill` argument out of a possibly-truncated tool input blob."""
    try:
        return json.loads(accumulated).get("skill", "")
    except json.JSONDecodeError:
        marker = '"skill":'
        if marker in accumulated:
            tail = accumulated.split(marker, 1)[1].strip()
            if tail.startswith('"'):
                return tail[1:].split('"', 1)[0]
        return ""


def _classify(tool: str, payload: str, skill_name: str, probe_name: str | None) -> tuple[str, str]:
    """Map a first tool call to (outcome, fired name)."""
    if tool == "Skill":
        fired = _skill_from_json(payload)
        if probe_name and probe_name in payload:
            return PROBE, probe_name
        if matches_skill(fired, skill_name):
            return SELF, fired
        return (OTHER, fired) if fired else (NONE, "")
    if tool == "Read":
        # Reading the skill file is the pre-Skill-tool way of triggering.
        if probe_name and probe_name in payload:
            return PROBE, probe_name
        if f"/{skill_name}/SKILL.md" in payload:
            return SELF, skill_name
        return OTHER, ""
    return OTHER, ""


def run_single_query(
    query: str,
    skill_name: str,
    skill_description: str,
    timeout: int,
    cwd: str,
    model: str | None = None,
    mode: str = "live",
    isolate: str | None = None,
) -> tuple[str, str]:
    """Run a single query; return (outcome, name of the skill that fired).

    In probe mode, creates a command file in .claude/commands/ so the candidate
    description appears in Claude's available-skills list. In live mode nothing
    is written and the installed skill set answers the query as-is.

    Uses --include-partial-messages to detect triggering early from stream
    events (content_block_start) rather than waiting for the full assistant
    message, which only arrives after tool execution.
    """
    command_file = None
    probe_name = None
    private_root = None

    try:
        if mode == "probe":
            unique_id = uuid.uuid4().hex[:8]
            probe_name = f"{skill_name}-skill-{unique_id}"
            # Each run gets its OWN project root. Sharing one means every
            # concurrent run's probe file is visible to every other run, and a
            # session that invokes a sibling's probe carries a different UUID --
            # so it is classified OTHER and scored as a miss even though the
            # candidate description is what triggered. That undercounts the
            # trigger rate, and undercounts it more the more workers are used.
            private_root = Path(tempfile.mkdtemp(prefix="probe-run-"))
            cwd = str(private_root)
            project_commands_dir = private_root / ".claude" / "commands"
            command_file = project_commands_dir / f"{probe_name}.md"
            project_commands_dir.mkdir(parents=True, exist_ok=True)
            # Use YAML block scalar to avoid breaking on quotes in description
            indented_desc = "\n  ".join(skill_description.split("\n"))
            command_file.write_text(
                f"---\n"
                f"description: |\n"
                f"  {indented_desc}\n"
                f"---\n\n"
                f"# {skill_name}\n\n"
                f"This skill handles: {skill_description}\n"
            )

        cmd = [
            "claude",
            "-p", query,
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        if model:
            cmd.extend(["--model", model])
        if isolate:
            # Hide the installed copy of the skill from this run only.
            cmd.extend(["--settings", isolate])

        # Remove CLAUDECODE env var to allow nesting claude -p inside a
        # Claude Code session. The guard is for interactive terminal conflicts;
        # programmatic subprocess usage is safe.
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        # Own process group, so the whole subtree can be reaped as a unit --
        # `claude` spawns its own children, and killing only the direct child
        # leaves those running.
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            pgid = process.pid
        _ACTIVE_PGIDS.add(pgid)
        _record_pid(process.pid)

        start_time = time.time()
        buffer = ""
        pending_tool_name = None
        accumulated_json = ""

        try:
            while time.time() - start_time < timeout:
                if process.poll() is not None:
                    remaining = process.stdout.read()
                    if remaining:
                        buffer += remaining.decode("utf-8", errors="replace")
                    break

                ready, _, _ = select.select([process.stdout], [], [], 1.0)
                if not ready:
                    continue

                chunk = os.read(process.stdout.fileno(), 8192)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Early detection via stream events
                    if event.get("type") == "stream_event":
                        se = event.get("event", {})
                        se_type = se.get("type", "")

                        if se_type == "content_block_start":
                            cb = se.get("content_block", {})
                            if cb.get("type") == "tool_use":
                                tool_name = cb.get("name", "")
                                if tool_name in ("Skill", "Read"):
                                    pending_tool_name = tool_name
                                    accumulated_json = ""
                                else:
                                    # First tool call was something else entirely.
                                    return OTHER, ""

                        elif se_type == "content_block_delta" and pending_tool_name:
                            delta = se.get("delta", {})
                            if delta.get("type") == "input_json_delta":
                                accumulated_json += delta.get("partial_json", "")
                                if probe_name and probe_name in accumulated_json:
                                    return PROBE, probe_name

                        elif se_type in ("content_block_stop", "message_stop"):
                            if pending_tool_name:
                                return _classify(
                                    pending_tool_name, accumulated_json, skill_name, probe_name
                                )
                            if se_type == "message_stop":
                                return NONE, ""

                    # Fallback: full assistant message
                    elif event.get("type") == "assistant":
                        message = event.get("message", {})
                        for content_item in message.get("content", []):
                            if content_item.get("type") != "tool_use":
                                continue
                            tool_name = content_item.get("name", "")
                            payload = json.dumps(content_item.get("input", {}))
                            return _classify(tool_name, payload, skill_name, probe_name)

                    elif event.get("type") == "result":
                        return NONE, ""
        finally:
            # Reap the whole group on any exit path (return, exception, timeout).
            # Killing the group rather than the process gets whatever `claude`
            # spawned; leaving those behind is the same billing leak at one
            # remove.
            _kill_pgid(pgid)
            _ACTIVE_PGIDS.discard(pgid)
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

        return NONE, ""
    finally:
        if command_file is not None and command_file.exists():
            command_file.unlink()
        if private_root is not None:
            shutil.rmtree(private_root, ignore_errors=True)


def run_eval(
    eval_set: list[dict],
    skill_name: str,
    description: str,
    num_workers: int,
    timeout: int,
    project_root: Path,
    runs_per_query: int = 1,
    trigger_threshold: float = 0.5,
    model: str | None = None,
    mode: str = "live",
    cwd: Path | None = None,
    isolate: str | None = None,
) -> dict:
    """Run the full eval set and return results."""
    results = []
    # Leave a trail of nested-session PIDs. Nothing in-process survives SIGKILL,
    # so this is the only way `--cleanup` can find them afterwards.
    if not os.environ.get(PIDFILE_ENV):
        pidfile = Path(tempfile.gettempdir()) / f"skill-eval-pids-{os.getpid()}.txt"
        os.environ[PIDFILE_ENV] = str(pidfile)
        # Only needed if this process dies hard; on a clean exit it is litter,
        # and stale files would make `--cleanup` noisier every run.
        atexit.register(lambda: pidfile.unlink(missing_ok=True))
    # Probe mode needs the command file under the project root Claude will scan;
    # live mode wants a directory with no source in it, or the model reads code
    # instead of choosing a skill.
    run_cwd = str(cwd) if cwd else str(project_root)

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    run_single_query,
                    item["query"],
                    skill_name,
                    description,
                    timeout,
                    run_cwd,
                    model,
                    mode,
                    isolate,
                )
                future_to_info[future] = (item, run_idx)

        query_outcomes: dict[str, list[tuple[str, str]]] = {}
        query_items: dict[str, dict] = {}
        for future in as_completed(future_to_info):
            item, _ = future_to_info[future]
            query = item["query"]
            query_items[query] = item
            if query not in query_outcomes:
                query_outcomes[query] = []
            try:
                query_outcomes[query].append(future.result())
            except Exception as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                query_outcomes[query].append((NONE, ""))

    # In probe mode a run won by the installed copy of the skill under test
    # measured nothing about the candidate description. Count it, don't score it.
    hit = PROBE if mode == "probe" else SELF
    total_contaminated = 0

    for query, outcomes in query_outcomes.items():
        item = query_items[query]
        contaminated = sum(1 for o, _ in outcomes if mode == "probe" and o == SELF)
        total_contaminated += contaminated
        scored = [o for o in outcomes if not (mode == "probe" and o[0] == SELF)]
        triggers = sum(1 for o, _ in scored if o == hit)
        trigger_rate = triggers / len(scored) if scored else 0.0
        should_trigger = item["should_trigger"]
        if not scored:
            # Every run was contaminated: unmeasured, which is not the same as
            # failed. Reporting it as a failure is the bug this mode exists to
            # avoid re-introducing.
            did_pass = None
        elif should_trigger:
            did_pass = trigger_rate >= trigger_threshold
        else:
            did_pass = trigger_rate < trigger_threshold
        results.append({
            "query": query,
            "should_trigger": should_trigger,
            "trigger_rate": trigger_rate,
            "triggers": triggers,
            "runs": len(scored),
            "contaminated": contaminated,
            "fired": [name for _, name in outcomes],
            "pass": did_pass,
        })

    passed = sum(1 for r in results if r["pass"] is True)
    failed = sum(1 for r in results if r["pass"] is False)
    unmeasured = sum(1 for r in results if r["pass"] is None)
    total = len(results)

    # The number to compare descriptions on. Per-query pass/fail discretizes a
    # rate into a coin flip and is not a usable signal at small sample sizes --
    # `mde` states how big a difference this run could actually detect.
    positive_rate, positive_obs = stats.aggregate_rate(results)
    negative_rate, negative_obs = stats.aggregate_rate(
        [r for r in results if not r["should_trigger"]], positives_only=False
    )

    return {
        "skill_name": skill_name,
        "description": description,
        "mode": mode,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "unmeasured": unmeasured,
            "contaminated_runs": total_contaminated,
            "positive_rate": positive_rate,
            "positive_observations": positive_obs,
            "positive_ci": stats.wilson_ci(positive_rate, positive_obs),
            "negative_rate": negative_rate,
            "negative_observations": negative_obs,
            "mde": stats.mde(positive_obs),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Run trigger evaluation for a skill description")
    parser.add_argument("--eval-set", help="Path to eval set JSON file")
    parser.add_argument("--skill-path", help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override description to test (implies --mode probe)")
    parser.add_argument("--mode", choices=["live", "probe", "auto"], default="auto",
                        help="live: measure the installed skill. probe: inject a candidate "
                             "description under a throwaway name. auto (default): probe when "
                             "--description is given, live otherwise.")
    parser.add_argument("--cwd", default=None,
                        help="Directory to run queries from. Defaults to the project root in "
                             "probe mode and a fresh empty temp dir in live mode -- a cwd full "
                             "of source sends the model reading code instead of choosing a skill.")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold")
    parser.add_argument("--isolate", dest="isolate", action="store_true", default=None,
                        help="Hide the installed copy of this skill from each nested run via "
                             "--settings. Default: on in probe mode when the skill is installed "
                             "as a plugin. Disables the whole plugin, so sibling skills go too.")
    parser.add_argument("--no-isolate", dest="isolate", action="store_false",
                        help="Measure against the skill set exactly as installed.")
    parser.add_argument("--model", default=None, help="Model to use for claude -p (default: user's configured model)")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    parser.add_argument("--cleanup", nargs="?", const="", metavar="PIDFILE",
                        help="Kill nested sessions left over from a hard-killed run "
                             "and exit. With no argument, sweeps every "
                             "skill-eval-pids-*.txt in the temp dir.")
    parser.add_argument("--dry-run", action="store_true",
                        help="With --cleanup, list what would be killed.")
    args = parser.parse_args()

    if args.cleanup is not None:
        files = ([args.cleanup] if args.cleanup
                 else sorted(glob.glob(str(Path(tempfile.gettempdir()) / "skill-eval-pids-*.txt"))))
        total = 0
        for f in files:
            hit = sweep_orphans(f, dry_run=args.dry_run)
            total += len(hit)
            if hit:
                verb = "would kill" if args.dry_run else "killed"
                print(f"{f}: {verb} {len(hit)} nested session(s): "
                      f"{', '.join(map(str, hit))}")
            if not args.dry_run:
                try:
                    os.unlink(f)
                except OSError:
                    pass
        print(f"{'would kill' if args.dry_run else 'killed'} {total} orphaned session(s) "
              f"across {len(files)} file(s)")
        sys.exit(0)

    if not args.eval_set or not args.skill_path:
        parser.error("--eval-set and --skill-path are required (or use --cleanup)")

    eval_set = json.loads(Path(args.eval_set).read_text())
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
        sys.exit(1)

    name, original_description, content = parse_skill_md(skill_path)
    description = args.description or original_description
    project_root = find_project_root()

    mode = args.mode
    if mode == "auto":
        mode = "probe" if args.description else "live"

    if args.cwd:
        cwd = Path(args.cwd)
    elif mode == "probe":
        # Ignored: probe mode builds a private project root per run (see
        # run_single_query). Kept non-None so the plumbing stays uniform.
        cwd = project_root
    else:
        cwd = Path(tempfile.mkdtemp(prefix="trigger-eval-"))

    # Isolation only makes sense in probe mode: in live mode the installed skill
    # IS the thing being measured, so hiding it would measure nothing.
    isolate = None
    if mode == "probe" and args.isolate is not False:
        isolate = isolation_settings(name)
        if isolate is None and args.isolate:
            print(f"Note: --isolate requested but '{name}' is not installed as a plugin; "
                  f"nothing to hide.", file=sys.stderr)
    elif mode == "live" and args.isolate:
        print("Note: --isolate ignored in live mode -- the installed skill is what "
              "live mode measures.", file=sys.stderr)

    if args.verbose:
        print(f"Mode: {mode}  cwd: {cwd}"
              + (f"  isolating: {', '.join(plugin_keys_for(name))}" if isolate else ""),
              file=sys.stderr)
        print(f"Evaluating: {description}", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_name=name,
        description=description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        project_root=project_root,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
        mode=mode,
        cwd=cwd,
        isolate=isolate,
    )

    contaminated = output["summary"]["contaminated_runs"]
    if contaminated:
        print(
            f"\nWARNING: {contaminated} run(s) were won by the INSTALLED '{name}' skill, not the\n"
            f"probe. Those runs say nothing about the candidate description and were excluded\n"
            f"from the rates below. If most runs are contaminated the result is not a\n"
            f"measurement -- uninstall the skill or use --mode live to test the shipped text.",
            file=sys.stderr,
        )

    if args.verbose:
        summary = output["summary"]
        unmeasured = f", {summary['unmeasured']} unmeasured" if summary["unmeasured"] else ""
        lo, hi = summary["positive_ci"]
        print(
            f"Positive trigger rate: {summary['positive_rate']:.3f} [{lo:.3f}-{hi:.3f}] "
            f"over {summary['positive_observations']} observations\n"
            f"  Detectable difference vs another description at this sample size: "
            f"{summary['mde']:.3f}\n"
            f"Negative trigger rate:  {summary['negative_rate']:.3f} "
            f"({summary['negative_observations']} observations)",
            file=sys.stderr,
        )
        print(f"Per-query: {summary['passed']}/{summary['total']} passed{unmeasured}", file=sys.stderr)
        for r in output["results"]:
            status = "UNMEAS" if r["pass"] is None else ("PASS" if r["pass"] else "FAIL")
            rate_str = f"{r['triggers']}/{r['runs']}"
            others = sorted({n for n in r["fired"] if n and not matches_skill(n, name)})
            extra = f"  -> {', '.join(others)}" if others else ""
            print(f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}{extra}", file=sys.stderr)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
