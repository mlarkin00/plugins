#!/usr/bin/env python3
"""Commit and push the session's usage counts.

Increments accumulate in the counts file during the session; this pushes them
in one batch rather than per invocation, keeping history to roughly one commit
per session instead of one per skill call.

Both runtimes call this, but they get one batch by different means:

  * Claude Code fires it from `SessionEnd` — once, at the natural end of a
    session, so no throttling is wanted or applied.
  * Antigravity has no session-end event. The nearest equivalent is `Stop`,
    which fires at the end of *every* agent turn, so the hook passes
    `--min-interval` to collapse a session's turns into one commit. This
    replaces the `sync-usage` sidecar, which never ran: the agy CLI does not
    start a sidecar manager at all (see `.agents/wiki/antigravity/`).

The git work runs in a detached worker, not inline. Both runtimes cancel a hook
that is still running when the turn or the session ends, and the push is a
network round trip — around a second on a good link, which does not fit the
budget. Claude Code is the tight one: it allows the whole SessionEnd batch
1.5s, and derives that deadline only from hooks declared in settings.json, so
the `timeout` this plugin declares does not raise it. Pass --foreground to do
the work in this process instead; the tests use it to stay deterministic.

No-ops when SKILL_USAGE_REPO is unset, when nothing changed, when the repo is
mid-merge/rebase, or when throttled. Always exits 0.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import usage_lib  # noqa: E402

TIMEOUT = 15
SELF = os.path.realpath(__file__)

CACHE_ROOT = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
STATE_PATH = os.path.join(CACHE_ROOT, "skill-usage", "last-sync")


def relaunch_detached(argv: list[str]) -> bool:
    """Re-run this script in its own session and return without waiting.

    A plain background process is not enough. Claude Code spawns the hook into
    its own process group and, on cancellation, signals the whole group, so a
    worker that stayed in it would be killed alongside the hook. start_new_session
    puts the worker in a session of its own, out of reach of that group signal.

    The stdio redirects are just as load-bearing: the runner waits for the
    hook's stdout and stderr to close, so a worker holding the inherited pipes
    open would keep the session waiting exactly as long as running inline did.

    Returns False if the worker could not be started, so the caller can fall
    back to doing the work here rather than dropping the sync.
    """
    try:
        subprocess.Popen(
            [sys.executable, SELF, "--foreground", *argv],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def mid_operation(repo: str) -> bool:
    """True during a merge/rebase/cherry-pick.

    Committing into someone else's half-finished operation would entangle the
    counts with conflict resolution, so the sync waits for a later session.
    """
    result = git(repo, "rev-parse", "--git-dir")
    if result.returncode != 0:
        return True
    git_dir = os.path.join(repo, result.stdout.strip())
    markers = ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply")
    return any(os.path.exists(os.path.join(git_dir, m)) for m in markers)


def throttled(min_interval: float) -> bool:
    """True when a sync attempt finished less than min_interval seconds ago.

    Read before the git work so a throttled turn costs a stat, not a subprocess.
    A missing or unreadable state file means "never synced", which lets the
    commit through — failing open keeps counts flowing if the cache is wiped.
    """
    if min_interval <= 0:
        return False
    try:
        with open(STATE_PATH) as f:
            last = float(f.read().strip())
    except (OSError, ValueError):
        return False
    return (time.time() - last) < min_interval


def record_sync() -> None:
    """Stamp the throttle clock. Only ever called once the push has returned.

    Ordering is the point. Stamped before the push, a worker killed mid-push
    left behind a stamp for a sync that never landed, and the throttle then
    skipped the retry. Stamped after, a killed worker leaves no stamp at all
    and the next turn picks the work up.

    A push that fails cleanly — offline, say — still stamps. The throttle exists
    to collapse a session's turns into one commit, and withholding the stamp on
    failure would make an offline machine commit on every turn instead.
    """
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass  # a missing stamp only costs an extra attempt next turn


def upstream(repo: str) -> str | None:
    result = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ref = result.stdout.strip()
    return ref if result.returncode == 0 and ref else None


def only_our_commits(repo: str, ref: str, counts: str) -> bool:
    """True when every unpushed commit touches nothing but this machine's shard.

    The gate on rebasing. Sharding makes a rebase of our own sync commits
    conflict-free by construction, but the user's real work may also be sitting
    unpushed in this repo — it is their authoring checkout, not a telemetry
    sink. Rewriting their commits to deliver a usage count would be a terrible
    trade, so if anything unrelated is ahead, we leave the branch alone and let
    the count ride along with their next push.
    """
    listing = git(repo, "rev-list", "%s..HEAD" % ref)
    if listing.returncode != 0:
        return False
    for sha in listing.stdout.split():
        shown = git(repo, "show", "--pretty=", "--name-only", sha)
        if shown.returncode != 0:
            return False
        touched = [line.strip() for line in shown.stdout.splitlines() if line.strip()]
        if any(path != counts for path in touched):
            return False
    return True


def push(repo: str, counts: str) -> None:
    """Push, recovering from the one rejection we can safely resolve.

    A plain push fails as soon as another machine has pushed its own shard, and
    without recovery the branch simply stays ahead forever — the counts are
    committed locally and never reach anyone. Rebasing onto the fetched
    upstream fixes that, and cannot conflict, because no other machine writes
    this file.
    """
    if git(repo, "push").returncode == 0:
        return

    ref = upstream(repo)
    if not ref or git(repo, "fetch", "--quiet").returncode != 0:
        return
    if not only_our_commits(repo, ref, counts):
        return

    if git(repo, "rebase", ref).returncode != 0:
        git(repo, "rebase", "--abort")
        return
    git(repo, "push")  # still failing just leaves it for the next session


def sync(min_interval: float) -> int:
    """Commit this machine's shard and push it. The slow half."""
    if throttled(min_interval):
        return 0

    repo = usage_lib.resolve_repo()
    if not repo or mid_operation(repo):
        return 0

    counts = usage_lib.counts_relpath()
    if not os.path.exists(os.path.join(repo, counts)):
        return 0

    status = git(repo, "status", "--porcelain", "--", counts)
    if status.returncode != 0 or not status.stdout.strip():
        return 0

    # A shard is untracked the first time a machine syncs, and `commit --only`
    # rejects a pathspec git does not know yet. Staging first covers both the
    # first run and every later one.
    if git(repo, "add", "--", counts).returncode != 0:
        return 0

    # --only commits this path alone, leaving any unrelated staged work in the
    # repo untouched.
    commit = git(
        repo, "commit", "--only", "--no-verify",
        "-m", "chore(active-skills): update skill usage counts",
        "--", counts,
    )
    if commit.returncode != 0:
        return 0

    push(repo, counts)
    record_sync()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-interval",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="skip if a commit landed within this window (0 = never skip)",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="do the git work in this process instead of detaching a worker",
    )
    args = parser.parse_args()

    # Checked here as well as in the worker so the Antigravity Stop hook, which
    # fires every turn, costs one stat rather than a spawned interpreter.
    if throttled(args.min_interval):
        return 0

    if not args.foreground and relaunch_detached(sys.argv[1:]):
        return 0

    return sync(args.min_interval)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException:
        sys.exit(0)
