#!/usr/bin/env python3
"""Install opencode plugins from the mlarkin00/plugins repo.

Symlinks TS plugin files into ~/.config/opencode/plugins/, adds skills.paths
to the global opencode config, and disables Claude Code plugin imports for
the plugins that now have native opencode equivalents.

Idempotent — safe to re-run. Use --uninstall to reverse.

Usage:
    python3 opencode/install.py              # install / update
    python3 opencode/install.py --uninstall   # remove
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
REPO_ROOT = os.path.dirname(HERE)

PLUGIN_TS_FILES = [
    "llm-wiki.ts",
    "memory-bank.ts",
    "active-skills.ts",
    "skill-usage.ts",
]

SKILL_DIRS = [
    os.path.join(REPO_ROOT, "memory-bank", "skills"),
    os.path.join(REPO_ROOT, "llm-wiki", "skills"),
    os.path.join(REPO_ROOT, "active-skills", "skills"),
]

CLAUDE_CODE_PLUGINS_TO_DISABLE = {
    "active-skills@mlarkin00-plugins": False,
    "llm-wiki@mlarkin00-plugins": False,
    "memory-bank@mlarkin00-plugins": False,
    "skill-usage@mlarkin00-plugins": False,
}

OPENCODE_PLUGINS_DIR = os.path.join(
    os.path.expanduser("~"), ".config", "opencode", "plugins"
)
OPENCODE_CONFIG = os.path.join(
    os.path.expanduser("~"), ".config", "opencode", "opencode.jsonc"
)
OMO_CONFIG = os.path.join(os.path.expanduser("~"), ".omo", "omo.jsonc")


# --- JSONC helpers ---

def strip_jsonc(text: str) -> str:
    """Remove JSONC comments so json.loads can parse the result."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    result: list[str] = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        c = text[i]
        if escape:
            result.append(c)
            escape = False
            i += 1
            continue
        if c == "\\":
            result.append(c)
            escape = True
            i += 1
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
            i += 1
            continue
        if not in_string and c == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        result.append(c)
        i += 1
    return "".join(result)


def parse_jsonc(path: str) -> dict:
    with open(path) as f:
        return json.loads(strip_jsonc(f.read()))


def find_matching_brace(text: str, open_pos: int) -> int:
    """Given the index of an opening {, return the index of its matching }."""
    depth = 0
    in_string = False
    escape = False
    for i in range(open_pos, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


# --- install actions ---

def install_symlinks() -> list[str]:
    """Symlink TS plugin files from the repo into ~/.config/opencode/plugins/."""
    os.makedirs(OPENCODE_PLUGINS_DIR, exist_ok=True)
    created: list[str] = []
    for name in PLUGIN_TS_FILES:
        source = os.path.join(REPO_ROOT, "opencode", "plugins", name)
        target = os.path.join(OPENCODE_PLUGINS_DIR, name)
        if not os.path.isfile(source):
            print(f"  SKIP {name} — source not found: {source}", file=sys.stderr)
            continue
        # Remove existing file or stale symlink
        if os.path.islink(target) or os.path.isfile(target):
            os.unlink(target)
        elif os.path.isdir(target):
            import shutil
            shutil.rmtree(target)
        os.symlink(source, target)
        created.append(name)
    return created


def install_skills_paths() -> bool:
    """Add skills.paths to the global opencode config. Returns True if changed."""
    if not os.path.isfile(OPENCODE_CONFIG):
        print(f"  SKIP — config not found: {OPENCODE_CONFIG}", file=sys.stderr)
        return False

    text = open(OPENCODE_CONFIG).read()
    try:
        parsed = json.loads(strip_jsonc(text))
    except json.JSONDecodeError as e:
        print(f"  SKIP — config parse error: {e}", file=sys.stderr)
        return False

    existing_paths = parsed.get("skills", {}).get("paths", [])
    needed = [p for p in SKILL_DIRS if p not in existing_paths]
    if not needed:
        return False  # Already configured

    # String insertion: add missing paths to skills.paths
    if "skills" in parsed:
        # skills key exists — add missing paths to the array
        all_paths = existing_paths + needed
        new_skills = json.dumps({"paths": all_paths}, indent=2)
        # Replace the existing "skills": {...} block
        # Find "skills" key position
        skills_match = re.search(r'"skills"\s*:\s*\{', text)
        if not skills_match:
            print("  SKIP — could not find skills key for insertion", file=sys.stderr)
            return False
        skills_open = text.index("{", skills_match.start())
        skills_close = find_matching_brace(text, skills_open)
        # Preserve indentation
        before = text[:skills_match.start()]
        indent = "  "  # top-level key indentation
        after = text[skills_close + 1:]
        new_text = before + indent + '"skills": ' + json.dumps({"paths": all_paths}, indent=2).replace("\n", "\n" + indent) + after
        with open(OPENCODE_CONFIG, "w") as f:
            f.write(new_text)
    else:
        # No skills key — insert before the final closing brace
        last_brace = text.rfind("}")
        if last_brace == -1:
            print("  SKIP — could not find closing brace", file=sys.stderr)
            return False
        before = text[:last_brace].rstrip()
        if not before.endswith(","):
            before += ","
        all_paths = needed
        skills_json = json.dumps({"paths": all_paths}, indent=2)
        new_text = before + '\n  "skills": ' + skills_json.replace("\n", "\n  ") + "\n}"
        with open(OPENCODE_CONFIG, "w") as f:
            f.write(new_text)
    return True


def install_plugins_override() -> bool:
    """Add claude_code.plugins_override to ~/.omo/omo.jsonc. Returns True if changed."""
    if not os.path.isfile(OMO_CONFIG):
        print(f"  SKIP — config not found: {OMO_CONFIG}", file=sys.stderr)
        return False

    text = open(OMO_CONFIG).read()
    try:
        parsed = json.loads(strip_jsonc(text))
    except json.JSONDecodeError as e:
        print(f"  SKIP — config parse error: {e}", file=sys.stderr)
        return False

    oc = parsed.get("[opencode]", {})
    existing_override = oc.get("claude_code", {}).get("plugins_override", {})
    needed = {
        k: v for k, v in CLAUDE_CODE_PLUGINS_TO_DISABLE.items()
        if k not in existing_override
    }
    if not needed:
        return False  # Already configured

    # Find the [opencode] object's closing brace
    oc_key_match = re.search(r'"\[opencode\]"\s*:\s*\{', text)
    if not oc_key_match:
        print("  SKIP — could not find [opencode] section", file=sys.stderr)
        return False
    oc_open = text.index("{", oc_key_match.start())
    oc_close = find_matching_brace(text, oc_open)

    # Build the merged plugins_override (existing + needed)
    merged_override = {**existing_override, **CLAUDE_CODE_PLUGINS_TO_DISABLE}
    claude_code_json = json.dumps(
        {"plugins": True, "plugins_override": merged_override}, indent=4
    )

    # Check if claude_code key already exists in [opencode]
    if "claude_code" in oc:
        # Replace the existing claude_code block
        cc_match = re.search(r'"claude_code"\s*:\s*\{', text[oc_open:oc_close])
        if cc_match:
            cc_start = oc_open + cc_match.start()
            cc_open = text.index("{", cc_start)
            cc_close = find_matching_brace(text, cc_open)
            before = text[:cc_start]
            after = text[cc_close + 1:]
            indent = "    "
            new_text = before + indent + '"claude_code": ' + claude_code_json.replace("\n", "\n" + indent) + after
            with open(OMO_CONFIG, "w") as f:
                f.write(new_text)
            return True
    else:
        # Insert new claude_code key before the [opencode] closing brace
        before = text[:oc_close].rstrip()
        if not before.endswith(","):
            before += ","
        after = text[oc_close:]
        indent = "    "
        new_text = before + '\n' + indent + '"claude_code": ' + claude_code_json.replace("\n", "\n" + indent) + after
        with open(OMO_CONFIG, "w") as f:
            f.write(new_text)
        return True

    return False


def _remove_key_block(text: str, key_start: int, value_close: int) -> str:
    """Remove a key-value block from JSONC text, fixing exactly one comma.

    A JSON object has commas *between* entries. Removing one entry must remove
    exactly one of the two surrounding commas — not both, not neither.
    """
    before = text[:key_start].rstrip()
    after = text[value_close + 1:]
    if before.endswith(","):
        before = before[:-1]
    elif after.lstrip().startswith(","):
        comma_idx = after.index(",")
        after = after[:comma_idx] + after[comma_idx + 1:]
    return before + after


# --- uninstall actions ---

def uninstall_symlinks() -> list[str]:
    """Remove symlinks from ~/.config/opencode/plugins/."""
    removed: list[str] = []
    for name in PLUGIN_TS_FILES:
        target = os.path.join(OPENCODE_PLUGINS_DIR, name)
        if os.path.islink(target):
            os.unlink(target)
            removed.append(name)
        elif os.path.isfile(target):
            # Check if it points to our repo
            try:
                if os.path.realpath(target).startswith(REPO_ROOT):
                    os.unlink(target)
                    removed.append(name)
            except OSError:
                pass
    return removed


def uninstall_skills_paths() -> bool:
    """Remove our skill dirs from skills.paths. Returns True if changed."""
    if not os.path.isfile(OPENCODE_CONFIG):
        return False
    text = open(OPENCODE_CONFIG).read()
    try:
        parsed = json.loads(strip_jsonc(text))
    except json.JSONDecodeError:
        return False

    skills = parsed.get("skills", {})
    paths = skills.get("paths", [])
    remaining = [p for p in paths if p not in SKILL_DIRS]
    if len(remaining) == len(paths):
        return False  # Nothing to remove

    if not remaining:
        # Remove the entire skills key
        skills_match = re.search(r'"skills"\s*:\s*\{', text)
        if not skills_match:
            return False
        skills_open = text.index("{", skills_match.start())
        skills_close = find_matching_brace(text, skills_open)
        new_text = _remove_key_block(text, skills_match.start(), skills_close)
        with open(OPENCODE_CONFIG, "w") as f:
            f.write(new_text)
    else:
        # Update the paths array
        skills_match = re.search(r'"skills"\s*:\s*\{', text)
        if not skills_match:
            return False
        skills_open = text.index("{", skills_match.start())
        skills_close = find_matching_brace(text, skills_open)
        before = text[:skills_match.start()]
        after = text[skills_close + 1:]
        indent = "  "
        new_skills = json.dumps({"paths": remaining}, indent=2)
        new_text = before + indent + '"skills": ' + new_skills.replace("\n", "\n" + indent) + after
        with open(OPENCODE_CONFIG, "w") as f:
            f.write(new_text)
    return True


def uninstall_plugins_override() -> bool:
    """Remove claude_code.plugins_override from omo.jsonc. Returns True if changed."""
    if not os.path.isfile(OMO_CONFIG):
        return False
    text = open(OMO_CONFIG).read()
    try:
        parsed = json.loads(strip_jsonc(text))
    except json.JSONDecodeError:
        return False

    cc = parsed.get("[opencode]", {}).get("claude_code", {})
    override = cc.get("plugins_override", {})
    remaining = {
        k: v for k, v in override.items()
        if k not in CLAUDE_CODE_PLUGINS_TO_DISABLE
    }
    if len(remaining) == len(override):
        return False  # Nothing to remove

    # Find and replace the claude_code block
    oc_key_match = re.search(r'"\[opencode\]"\s*:\s*\{', text)
    if not oc_key_match:
        return False
    oc_open = text.index("{", oc_key_match.start())
    oc_close = find_matching_brace(text, oc_open)

    cc_match = re.search(r'"claude_code"\s*:\s*\{', text[oc_open:oc_close])
    if not cc_match:
        return False
    cc_start = oc_open + cc_match.start()
    cc_open = text.index("{", cc_start)
    cc_close = find_matching_brace(text, cc_open)

    if not remaining:
        # Remove the entire claude_code key
        new_text = _remove_key_block(text, cc_start, cc_close)
    else:
        # Update with remaining entries
        new_cc = json.dumps(
            {"plugins": True, "plugins_override": remaining}, indent=4
        )
        before = text[:cc_start]
        after = text[cc_close + 1:]
        indent = "    "
        new_text = before + indent + '"claude_code": ' + new_cc.replace("\n", "\n" + indent) + after

    with open(OMO_CONFIG, "w") as f:
        f.write(new_text)
    return True


# --- main ---

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true", help="Remove the plugins")
    args = parser.parse_args()

    if args.uninstall:
        print("Uninstalling opencode plugins...")
        removed = uninstall_symlinks()
        print(f"  Removed symlinks: {', '.join(removed) or 'none'}")
        if uninstall_skills_paths():
            print("  Removed skills.paths from opencode config")
        if uninstall_plugins_override():
            print("  Removed plugins_override from omo config")
        print("Done. Restart opencode for changes to take effect.")
        return 0

    print(f"Installing opencode plugins from {REPO_ROOT}")
    print()

    # 1. Symlink TS plugins
    created = install_symlinks()
    print(f"Symlinked {len(created)} plugin files:")
    for name in created:
        print(f"  ~/.config/opencode/plugins/{name} → {REPO_ROOT}/opencode/plugins/{name}")
    print()

    # 2. Add skills.paths
    if install_skills_paths():
        print(f"Added skills.paths to {OPENCODE_CONFIG}")
    else:
        print(f"skills.paths already configured in {OPENCODE_CONFIG}")
    print()

    # 3. Disable Claude Code imports
    if install_plugins_override():
        print(f"Added claude_code.plugins_override to {OMO_CONFIG}")
    else:
        print(f"plugins_override already configured in {OMO_CONFIG}")
    print()

    print("Done. Restart opencode for changes to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
