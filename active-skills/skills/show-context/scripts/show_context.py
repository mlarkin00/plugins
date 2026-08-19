#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Render the injected context of an agent session transcript.

The principle is harness-agnostic: the session transcript is ground truth and
introspection is not, so read the transcript and report what it actually
contains. The *mechanism* is not — every harness stores its session differently.
This script implements the **Claude Code** backend: it reads the JSONL
transcript under ``~/.claude/projects/`` and renders every ``attachment`` record
the harness injected (memory/instruction files, hook output, skill/agent/tool/
MCP listings, attached files, reminders).

In a non-Claude-Code harness it does not try to guess a foreign format. It
detects the harness and prints a pointer to that harness's native
session-introspection mechanism instead, so an agent following this skill is
never left to introspect. The transcript does NOT contain the system prompt,
so neither does this output.

Usage:
  show_context.py                          # current Claude Code session
  show_context.py --include messages       # + prompts, replies, tool results
  show_context.py --only nested_memory,hook
  show_context.py --session <uuid>
  show_context.py --transcript path.jsonl
  show_context.py --list-sessions
  show_context.py --inventory              # counts only, nothing dumped
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Claude Code backend only. Other harnesses have their own stores (e.g. OpenCode
# uses a SQLite DB) and are handled via HARNESS_POINTERS, not parsed here.
PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Printed when this script cannot read the session itself. Each entry must name
# the native mechanism an agent should use in that harness (read ground truth,
# never introspect) so an agent following this skill is never left to guess.
HARNESS_POINTERS = {
    "opencode": (
        "You are running inside OpenCode, which stores sessions in a SQLite "
        "database (~/.local/share/opencode/opencode.db), not a JSONL "
        "transcript. Use OpenCode's native session tools to read the ground "
        "truth instead of introspecting:\n"
        "  - session_list            list sessions (newest first)\n"
        "  - session_info <ses_id>   metadata + message count for a session\n"
        "  - session_read <ses_id>   the messages/history, with roles + times\n"
        "  - session_search \"<q>\"   full-text search across session messages\n"
        "Report what those return, verbatim, the same way this script would. "
        "Do not summarize away the dump, and do not answer from introspection."
    ),
    "unknown": (
        "No Claude Code session was found, and the current harness is not one "
        "this script reads directly. Apply the same principle with your "
        "harness's native session-transcript mechanism: find the ground-truth "
        "record of what was injected into this session (instruction files, "
        "hooks, skill/MCP listings, attached files) and report it verbatim. "
        "Do not answer from introspection. If your harness has no transcript, "
        "say so plainly rather than guessing."
    ),
}


def detect_harness():
    """Detect by env var, not by directory existence — one machine may have
    several harnesses installed, so a present store is not the current one."""
    if os.environ.get("CLAUDE_CODE_SESSION_ID") or os.environ.get("CLAUDECODE"):
        return "claude_code"
    if os.environ.get("OPENCODE"):
        return "opencode"
    return "unknown"

# Attachment types grouped into the sections used for rendering. Order here is
# the order sections appear in the output: the things people most often need to
# confirm (memory, hooks) come first.
SECTIONS = [
    ("nested_memory", "Memory & instruction files", ["nested_memory"]),
    ("hook", "Hook output", [
        "hook_success", "hook_non_blocking_error",
        "hook_blocking_error", "hook_system_message",
    ]),
    ("skills", "Skills", ["skill_listing", "invoked_skills"]),
    ("agents", "Agent listing", ["agent_listing_delta"]),
    ("tools", "Deferred tools", ["deferred_tools_delta"]),
    ("mcp", "MCP server instructions", ["mcp_instructions_delta"]),
    ("permissions", "Command permissions", ["command_permissions"]),
    ("files", "Files & directories in context", [
        "file", "directory", "edited_text_file",
        "compact_file_reference", "read_truncation_notice",
    ]),
    ("reminders", "Reminders & session state", [
        "task_reminder", "output_style", "date_change",
    ]),
    ("queued", "Queued commands", ["queued_command"]),
]

# Injected content that arrives as `user` records rather than attachments:
# slash-command bodies and skill bodies land here with isMeta set.
META_SECTION = ("meta", "Injected prompt content (slash commands, skill bodies)")


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def find_transcript(session_id=None, explicit=None):
    """Locate the transcript file.

    An explicit ``--transcript`` path works in any harness (the caller named a
    Claude Code JSONL to inspect). Otherwise this is the Claude Code backend,
    so a non-Claude-Code harness gets a pointer to its native session tools
    instead of a misleading "session not found" error.
    """
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_file():
            die(f"no such transcript: {p}")
        return p

    harness = detect_harness()
    if harness != "claude_code":
        print(HARNESS_POINTERS.get(harness, HARNESS_POINTERS["unknown"]))
        sys.exit(0)

    sid = session_id or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        die(
            "no Claude Code session id. Set --session or --transcript, or run "
            "inside a Claude Code session (CLAUDE_CODE_SESSION_ID)."
        )

    matches = list(PROJECTS_DIR.glob(f"**/{sid}.jsonl"))
    if not matches:
        die(f"no transcript found for session {sid} under {PROJECTS_DIR}")
    return max(matches, key=lambda p: p.stat().st_mtime)


def list_sessions():
    harness = detect_harness()
    if harness != "claude_code":
        print(HARNESS_POINTERS.get(harness, HARNESS_POINTERS["unknown"]))
        return
    rows = []
    for p in PROJECTS_DIR.glob("*/*.jsonl"):
        st = p.stat()
        rows.append((st.st_mtime, p.stem, p.parent.name, st.st_size))
    if not rows:
        die(f"no transcripts under {PROJECTS_DIR}")
    rows.sort(reverse=True)
    print(f"{'SESSION':38}  {'SIZE':>9}  PROJECT")
    for _, sid, project, size in rows:
        print(f"{sid:38}  {size:>9,}  {project}")


def load(path):
    records = []
    for n, line in enumerate(path.open(encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"warning: skipped malformed line {n}", file=sys.stderr)
    return records


def fence(text, lang=""):
    """Wrap text in a code fence long enough to survive nested fences."""
    text = text if isinstance(text, str) else json.dumps(text, indent=2)
    longest = 0
    run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    bar = "`" * max(3, longest + 1)
    return f"{bar}{lang}\n{text}\n{bar}"


def render_nested_memory(a):
    inner = a.get("content")
    path = a.get("path") or a.get("displayPath") or "(unknown path)"
    out = [f"**`{path}`**"]
    if isinstance(inner, dict):
        kind = inner.get("type")
        if kind:
            out.append(f"scope: {kind}")
        if inner.get("contentDiffersFromDisk"):
            out.append(
                "> injected copy differs from what is on disk now "
                "(`contentDiffersFromDisk: true`)"
            )
        body = inner.get("content", "")
    else:
        body = inner or ""
    out.append(fence(body, "markdown"))
    return "\n\n".join(out)


def render_hook(a):
    name = a.get("hookName", "?")
    event = a.get("hookEvent", "?")
    head = f"**{name}** — event `{event}`"
    bits = []
    if a.get("command"):
        bits.append(f"command: `{a['command']}`")
    if a.get("exitCode") is not None:
        bits.append(f"exit: {a['exitCode']}")
    if a.get("durationMs") is not None:
        bits.append(f"{a['durationMs']} ms")
    out = [head + (f"  \n{' · '.join(bits)}" if bits else "")]

    # `content` is what actually reached the context window; stdout/stderr are
    # shown only when they add something beyond it.
    content = a.get("content")
    if content:
        out.append("injected:\n" + fence(content))
    else:
        out.append("_injected no content_")
    for stream in ("stdout", "stderr", "blockingError"):
        val = a.get(stream)
        if val and val.strip() and val.strip() != (content or "").strip():
            out.append(f"{stream}:\n" + fence(val))
    return "\n\n".join(out)


def render_skill_listing(a):
    out = [f"{a.get('skillCount', '?')} skills"
           + ("  (initial listing)" if a.get("isInitial") else "  (update)")]
    if a.get("content"):
        out.append(fence(a["content"]))
    return "\n\n".join(out)


def render_delta(a, added_key, removed_key, lines_key=None, label="entries"):
    added = a.get(added_key) or []
    removed = a.get(removed_key) or []
    out = [f"+{len(added)} / -{len(removed)} {label}"
           + ("  (initial)" if a.get("isInitial") else "")]
    if added:
        out.append("added:\n" + fence("\n".join(map(str, added))))
    if removed:
        out.append("removed:\n" + fence("\n".join(map(str, removed))))
    if lines_key and a.get(lines_key):
        val = a[lines_key]
        text = "\n".join(val) if isinstance(val, list) else str(val)
        out.append("text as injected:\n" + fence(text))
    for extra in ("pendingMcpServers", "needsAuthMcpServers", "readdedNames"):
        if a.get(extra):
            out.append(f"{extra}: {', '.join(map(str, a[extra]))}")
    return "\n\n".join(out)


def render_file(a):
    name = a.get("displayPath") or a.get("filename") or "(unknown)"
    out = [f"**`{name}`**"]
    body = a.get("content") or a.get("snippet") or a.get("banner")
    if body:
        out.append(fence(body if isinstance(body, str)
                         else json.dumps(body, indent=2)))
    return "\n\n".join(out)


def render_generic(a):
    body = {k: v for k, v in a.items() if k != "type"}
    if set(body) == {"content"} and isinstance(body["content"], str):
        return fence(body["content"])
    return fence(json.dumps(body, indent=2, ensure_ascii=False), "json")


RENDERERS = {
    "nested_memory": render_nested_memory,
    "hook_success": render_hook,
    "hook_non_blocking_error": render_hook,
    "hook_blocking_error": render_hook,
    "hook_system_message": render_hook,
    "skill_listing": render_skill_listing,
    "agent_listing_delta": lambda a: render_delta(
        a, "addedTypes", "removedTypes", "addedLines", "agents"),
    "deferred_tools_delta": lambda a: render_delta(
        a, "addedNames", "removedNames", "addedLines", "tools"),
    "mcp_instructions_delta": lambda a: render_delta(
        a, "addedNames", "removedNames", "addedBlocks", "servers"),
    "file": render_file,
    "directory": render_file,
    "edited_text_file": render_file,
    "compact_file_reference": render_file,
    "read_truncation_notice": render_file,
}


def text_of(msg_content):
    """Flatten a message content field to plain text."""
    if isinstance(msg_content, str):
        return msg_content
    if not isinstance(msg_content, list):
        return ""
    parts = []
    for block in msg_content:
        if not isinstance(block, dict):
            continue
        t = block.get("type")
        if t == "text":
            parts.append(block.get("text", ""))
        elif t == "tool_use":
            parts.append(
                f"[tool_use: {block.get('name')}]\n"
                + json.dumps(block.get("input", {}), indent=2)[:100000]
            )
        elif t == "tool_result":
            c = block.get("content")
            parts.append("[tool_result]\n" + (c if isinstance(c, str)
                                              else json.dumps(c, indent=2)))
        elif t == "thinking":
            parts.append("[thinking]\n" + block.get("thinking", ""))
    return "\n\n".join(p for p in parts if p)


def collect(records, include_sidechains):
    """Bucket records into (section_key -> list of (record, attachment))."""
    buckets = {key: [] for key, _, _ in SECTIONS}
    buckets[META_SECTION[0]] = []
    unknown = []
    messages = []
    sidechain_count = 0

    type_to_section = {}
    for key, _, types in SECTIONS:
        for t in types:
            type_to_section[t] = key

    for rec in records:
        if rec.get("isSidechain") and not include_sidechains:
            sidechain_count += 1
            continue
        rtype = rec.get("type")

        if rtype == "attachment":
            a = rec.get("attachment") or {}
            key = type_to_section.get(a.get("type"))
            (buckets[key] if key else unknown).append((rec, a))
        elif rtype == "user" and rec.get("isMeta"):
            buckets[META_SECTION[0]].append((rec, None))
        elif rtype in ("user", "assistant"):
            messages.append(rec)

    return buckets, unknown, messages, sidechain_count


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Render the injected context of an agent session transcript. "
            "Reads Claude Code JSONL transcripts; in other harnesses prints a "
            "pointer to that harness's native session tools."
        ),
        epilog=(
            "examples:\n"
            "  show_context.py\n"
            "  show_context.py --only nested_memory,hook\n"
            "  show_context.py --include messages --session <uuid>\n"
            "  show_context.py --list-sessions\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--session", help="session UUID (default: current)")
    ap.add_argument("--transcript", help="explicit path to a .jsonl transcript")
    ap.add_argument("--include", choices=["messages", "all"],
                    help="also render conversation messages")
    ap.add_argument("--only", help="comma-separated section keys to render")
    ap.add_argument("--inventory", action="store_true",
                    help="print counts only, dump nothing")
    ap.add_argument("--include-sidechains", action="store_true",
                    help="include subagent records (excluded by default)")
    ap.add_argument("--list-sessions", action="store_true",
                    help="list known transcripts and exit")
    args = ap.parse_args()

    if args.list_sessions:
        list_sessions()
        return

    path = find_transcript(args.session, args.transcript)
    records = load(path)
    buckets, unknown, messages, sidechains = collect(
        records, args.include_sidechains)

    only = None
    if args.only:
        only = {s.strip() for s in args.only.split(",") if s.strip()}
        valid = {k for k, _, _ in SECTIONS} | {META_SECTION[0]}
        bad = only - valid
        if bad:
            die(f"unknown section(s): {', '.join(sorted(bad))}. "
                f"valid: {', '.join(sorted(valid))}")

    total = sum(len(v) for v in buckets.values()) + len(unknown)

    print(f"# Injected context — session `{path.stem}`\n")
    print(f"- transcript: `{path}`  ({path.stat().st_size:,} bytes)")
    print(f"- records: {len(records):,}  ·  injected items: {total}"
          f"  ·  messages: {len(messages)}")
    if sidechains:
        print(f"- excluded {sidechains} subagent (sidechain) record(s); "
              f"pass `--include-sidechains` to include them")
    print("- the system prompt is not stored in the transcript and is "
          "therefore not shown\n")

    # Inventory table — always printed, so an absent category is visible as
    # an absence rather than being silently omitted.
    print("| section | items |")
    print("|---|---|")
    for key, title, _ in SECTIONS:
        print(f"| `{key}` — {title} | {len(buckets[key])} |")
    print(f"| `{META_SECTION[0]}` — {META_SECTION[1]} "
          f"| {len(buckets[META_SECTION[0]])} |")
    if unknown:
        print(f"| unrecognized | {len(unknown)} |")
    print()

    if args.inventory:
        return

    sections = list(SECTIONS) + [(META_SECTION[0], META_SECTION[1], [])]
    for key, title, _ in sections:
        items = buckets[key]
        if only and key not in only:
            continue
        if not items:
            continue
        print(f"\n---\n\n## {title}  ({len(items)})\n")
        for i, (rec, a) in enumerate(items, 1):
            ts = rec.get("timestamp", "")
            if a is None:
                print(f"### {i}. injected prompt content  \n`{ts}`\n")
                print(fence(text_of(rec.get("message", {}).get("content"))))
            else:
                atype = a.get("type", "?")
                print(f"### {i}. `{atype}`  \n`{ts}`\n")
                print(RENDERERS.get(atype, render_generic)(a))
            print()

    if unknown and not only:
        print(f"\n---\n\n## Unrecognized attachment types  ({len(unknown)})\n")
        for i, (rec, a) in enumerate(unknown, 1):
            print(f"### {i}. `{a.get('type', '?')}`  "
                  f"\n`{rec.get('timestamp', '')}`\n")
            print(render_generic(a))
            print()

    if args.include in ("messages", "all"):
        print(f"\n---\n\n## Conversation messages  ({len(messages)})\n")
        for i, rec in enumerate(messages, 1):
            role = rec.get("type")
            src = rec.get("promptSource") or (
                (rec.get("origin") or {}).get("kind") if rec.get("origin")
                else None)
            tag = f" ({src})" if src else ""
            body = text_of(rec.get("message", {}).get("content"))
            if not body.strip():
                continue
            print(f"### {i}. {role}{tag}  \n`{rec.get('timestamp', '')}`\n")
            print(fence(body))
            print()


if __name__ == "__main__":
    main()
