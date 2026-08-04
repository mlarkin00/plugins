#!/usr/bin/env python3
"""Poll GitHub repository for updates and automatically pull them.

NOTE: This refresh systemd service should only be used with Jetski and Antigravity.
It should not be used with clients that have proper marketplace/plugin install/update
mechanisms (e.g., Claude Code).

Polls the remote tracking branch every hour (when invoked by systemd timer).
If there are local changes (uncommitted working tree changes or local commits),
it preserves them after the update unless there is an irreconcilable conflict.
If an irreconcilable conflict occurs, it restores the local repository state
to before the update attempt and adds a P0 item in .agents/TODO.md.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cmd(cmd, cwd=None, check=True):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        res = subprocess.run(
            cmd if isinstance(cmd, list) else cmd,
            shell=isinstance(cmd, str),
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
        )
        if check and res.returncode != 0:
            raise subprocess.CalledProcessError(
                res.returncode, cmd, res.stdout, res.stderr
            )
        return res.stdout.strip(), res.stderr.strip(), res.returncode
    except Exception as e:
        if check:
            raise e
        return "", str(e), -1


def add_p0_todo(repo_root, issue_description):
    """Add a P0 item explaining an irreconcilable conflict to .agents/TODO.md."""
    todo_path = Path(repo_root) / ".agents" / "TODO.md"
    if not todo_path.exists():
        todo_path.parent.mkdir(parents=True, exist_ok=True)
        todo_path.write_text(
            "# TODO\n\n## P0 — Address Immediately\n\n(none)\n\n## P1 — Important / Unblocking\n",
            encoding="utf-8",
        )

    content = todo_path.read_text(encoding="utf-8")
    if issue_description in content:
        # Avoid adding duplicate P0 items if timer runs repeatedly
        return

    lines = content.splitlines()
    new_lines = []
    in_p0_section = False
    p0_inserted = False
    replaced_none = False
    saw_p0_section = False

    for i, line in enumerate(lines):
        if line.strip().startswith("## P0"):
            in_p0_section = True
            saw_p0_section = True
            new_lines.append(line)
            continue
        elif line.strip().startswith("## ") and in_p0_section:
            if not p0_inserted and not replaced_none:
                if new_lines and new_lines[-1].strip() != "":
                    new_lines.append("")
                new_lines.append(f"- [ ] **[P0]** {issue_description}")
                new_lines.append("")
                p0_inserted = True
            in_p0_section = False
            new_lines.append(line)
            continue

        if in_p0_section:
            if line.strip() == "(none)":
                new_lines.append(f"- [ ] **[P0]** {issue_description}")
                p0_inserted = True
                replaced_none = True
                continue
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if in_p0_section and not p0_inserted and not replaced_none:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(f"- [ ] **[P0]** {issue_description}")
        new_lines.append("")
        p0_inserted = True

    if not p0_inserted and not replaced_none:
        if not saw_p0_section:
            if new_lines and new_lines[-1].strip() != "":
                new_lines.append("")
            new_lines.append("## P0 — Address Immediately")
            new_lines.append("")
        elif new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(f"- [ ] **[P0]** {issue_description}")
        new_lines.append("")

    updated_content = "\n".join(new_lines)
    if not updated_content.endswith("\n"):
        updated_content += "\n"

    todo_path.write_text(updated_content, encoding="utf-8")


def poll_and_update(cwd=None, dry_run=False):
    """Check remote tracking branch for updates and pull them while preserving local changes."""
    if cwd is None:
        cwd = REPO_ROOT

    cwd = Path(cwd).resolve()

    # Verify directory is a git repository
    _, _, code = run_cmd("git rev-parse --is-inside-work-tree", cwd=cwd, check=False)
    if code != 0:
        print("Error: Not a git repository", file=sys.stderr)
        return 1

    # Determine current branch
    branch, _, code = run_cmd("git symbolic-ref --short HEAD", cwd=cwd, check=False)
    if code != 0 or not branch:
        branch, _, code = run_cmd("git rev-parse --abbrev-ref HEAD", cwd=cwd, check=False)
        if code != 0 or not branch or branch == "HEAD":
            print("Info: Detached HEAD state. No branch to update.")
            return 0

    # Determine upstream branch
    upstream, _, code = run_cmd("git rev-parse --abbrev-ref @{u}", cwd=cwd, check=False)
    if code != 0 or not upstream or upstream == "HEAD":
        upstream = f"origin/{branch}"

    # Fetch latest remote changes first so refs/remotes are updated
    remote = upstream.split("/")[0] if "/" in upstream else "origin"
    if not dry_run:
        _, stderr, code = run_cmd(f"git fetch {remote}", cwd=cwd, check=False)
        if code != 0:
            print(f"Warning: git fetch failed: {stderr}", file=sys.stderr)
            # Exit 0 so transient network failures don't fail the timer or log P0 todos
            return 0

    # Verify upstream branch exists on remote after fetching
    _, _, code = run_cmd(f"git rev-parse --verify {upstream}", cwd=cwd, check=False)
    if code != 0:
        print(f"Info: Upstream tracking ref '{upstream}' not found.")
        return 0

    # Check divergence from upstream
    behind_str, _, _ = run_cmd(f"git rev-list --count HEAD..{upstream}", cwd=cwd)
    behind = int(behind_str) if behind_str else 0

    if behind == 0:
        print("Already up to date with remote.")
        return 0

    print(f"Branch '{branch}' is behind '{upstream}' by {behind} commit(s). Updating...")
    if dry_run:
        print("[dry-run] Would update from remote while keeping local changes.")
        return 0

    # Check if working directory is clean
    status_out, _, _ = run_cmd("git status --porcelain", cwd=cwd)
    is_clean = len(status_out.strip()) == 0

    original_head, _, _ = run_cmd("git rev-parse HEAD", cwd=cwd)
    original_head = original_head.strip()

    stashed = False
    if not is_clean:
        print("Stashing uncommitted local changes...")
        out, stderr, code = run_cmd(
            "git stash push -u -m 'poll-repo: auto-stash before update'",
            cwd=cwd,
            check=False,
        )
        if code != 0:
            issue = f"Git sync conflict when polling repository: failed to stash uncommitted changes on branch '{branch}' ({stderr})."
            add_p0_todo(cwd, issue)
            print(f"Error: {issue}", file=sys.stderr)
            return 1
        stashed = True

    # Attempt to rebase local commits on top of remote updates
    print(f"Rebasing local commits on top of {upstream}...")
    _, stderr, code = run_cmd(f"git rebase {upstream}", cwd=cwd, check=False)
    if code == 0:
        if stashed:
            print("Restoring stashed local changes...")
            _, pop_err, pop_code = run_cmd("git stash pop", cwd=cwd, check=False)
            if pop_code == 0:
                print("Successfully updated from remote and restored uncommitted changes.")
                return 0
            else:
                # Irreconcilable conflict during stash pop
                issue = f"Git sync conflict when polling repository: uncommitted local changes conflicted with remote updates on branch '{branch}'."
                print(f"Conflict detected: {issue} Rolling back...", file=sys.stderr)
                # Rollback failed stash pop and reset to original HEAD
                run_cmd("git reset --hard HEAD", cwd=cwd, check=False)
                run_cmd("git clean -fd", cwd=cwd, check=False)
                run_cmd(f"git reset --hard {original_head}", cwd=cwd, check=False)
                run_cmd("git stash pop", cwd=cwd, check=False)
                add_p0_todo(cwd, issue)
                return 1
        else:
            print("Successfully updated from remote.")
            return 0
    else:
        # Irreconcilable conflict during rebase
        issue = f"Git sync conflict when polling repository: local commits conflicted with remote updates on branch '{branch}'."
        print(f"Conflict detected: {issue} Aborting rebase...", file=sys.stderr)
        run_cmd("git rebase --abort", cwd=cwd, check=False)
        if stashed:
            run_cmd("git stash pop", cwd=cwd, check=False)
        add_p0_todo(cwd, issue)
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Poll GitHub repo for updates (NOTE: use ONLY with Jetski/Antigravity; do NOT use with Claude Code or clients with proper marketplace updates)."
    )
    parser.add_argument(
        "--cwd",
        type=str,
        default=None,
        help="Repository directory to update (default: repo root)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the check without changing repository state",
    )
    args = parser.parse_args()

    sys.exit(poll_and_update(cwd=args.cwd, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
