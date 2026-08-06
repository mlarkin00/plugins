#!/usr/bin/env python3
"""Prove the active-skills mirror step propagates upstream deletions.

The mirror is a dozen lines of rsync inside `sync-active-skills.yml`, and its
failure mode is silent success. rsync exclude rules are two-sided: the anchored
`- /*` that keeps non-skill entries out of the mirror ALSO protects matching
entries in the destination from `--delete`. A skill deleted upstream lost its
`+ /<name>/` rule, fell under `- /*`, and was therefore protected — so it kept
shipping from the marketplace while the workflow reported success. Discovered
2026-08-06 with the mirror at 40 skills against a source of 34.

This does not assert on the text of the workflow. It extracts the step's own
`run:` script and executes it against a fixture, so what is tested is what will
actually run: filter construction, the zero-skill abort, and the rsync flags
together. Evidence: `.agents/wiki/testing/rsync-protects-excluded.md`.

Usage: python3 .agents/scripts/check-sync-mirror.py
"""

import pathlib
import subprocess
import sys
import tempfile

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/sync-active-skills.yml"
STEP = "Mirror the source skills into the plugin"
PLUGIN = "active-skills"

# Files the plugin owns. They sit beside skills/, not in it, and no sync may
# ever touch them — this is the invariant that `716fb23` violated.
PLUGIN_FILES = [
    "plugin.json",
    ".claude-plugin/plugin.json",
    "hooks.json",
    "README.md",
    "scripts/gen-readme.sh",
]

failures = []


def check(condition, message):
    if not condition:
        failures.append(message)
    return condition


def mirror_script():
    """The `run:` body of the mirror step, as the workflow will execute it."""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for job in doc["jobs"].values():
        for step in job["steps"]:
            if step.get("name") == STEP:
                return step["run"]
    sys.exit(f"FAIL  no step named {STEP!r} in {WORKFLOW}")


def build_fixture(root, source_skills, dest_skills):
    """A source checkout and a plugin whose mirror is out of date."""
    source = root / ".source"
    for name in source_skills:
        (source / name).mkdir(parents=True)
        (source / name / "SKILL.md").write_text(f"# {name}\nfresh\n", encoding="utf-8")
    # Non-skill entries at the source root: present, but not ours to ship.
    (source / "docs").mkdir(parents=True)
    (source / "docs" / "README.md").write_text("docs\n", encoding="utf-8")
    (source / "README.md").write_text("readme\n", encoding="utf-8")

    plugin = root / PLUGIN
    for name in dest_skills:
        (plugin / "skills" / name).mkdir(parents=True)
        (plugin / "skills" / name / "SKILL.md").write_text("# stale\n", encoding="utf-8")
    for rel in PLUGIN_FILES:
        path = plugin / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("owned by the marketplace\n", encoding="utf-8")
    return plugin


def run_mirror(script, root):
    return subprocess.run(
        ["bash", "-c", script],
        cwd=root,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "PLUGIN": PLUGIN,
            "SOURCE_REPO": "mlarkin00/active-skills",
            "SOURCE_SHA": "0000000",
        },
        capture_output=True,
        text=True,
    )


def test_deletions_propagate(script):
    """A skill removed upstream must disappear from the mirror."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        plugin = build_fixture(
            root,
            source_skills=["alpha", "beta"],
            dest_skills=["alpha", "beta", "removed-one", "removed-two"],
        )
        result = run_mirror(script, root)
        if not check(result.returncode == 0, f"mirror exited {result.returncode}: {result.stderr}"):
            return

        mirrored = sorted(p.name for p in (plugin / "skills").iterdir())
        check(
            mirrored == ["alpha", "beta"],
            f"deletions did not propagate: skills/ holds {mirrored}, expected ['alpha', 'beta']. "
            "rsync is protecting excluded destination entries — is --delete-excluded still set?",
        )
        check(
            (plugin / "skills/alpha/SKILL.md").read_text(encoding="utf-8") == "# alpha\nfresh\n",
            "surviving skills were not updated from the source",
        )
        check(
            not (plugin / "skills/docs").exists() and not (plugin / "skills/README.md").exists(),
            "non-skill source entries were mirrored — they would install as phantom skills",
        )
        for rel in PLUGIN_FILES:
            check((plugin / rel).exists(), f"the sync destroyed the plugin's own {rel}")


def test_zero_skills_aborts(script):
    """A source with no skills must abort, never empty the mirror."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        plugin = build_fixture(root, source_skills=[], dest_skills=["alpha", "beta"])
        result = run_mirror(script, root)

        check(result.returncode != 0, "a source with zero skills was accepted instead of aborting")
        check(
            "No skills found" in (result.stdout + result.stderr),
            "the zero-skill abort did not explain itself",
        )
        survivors = sorted(p.name for p in (plugin / "skills").iterdir())
        check(
            survivors == ["alpha", "beta"],
            f"the aborted sync still emptied the mirror: {survivors}",
        )


def main():
    script = mirror_script()
    test_deletions_propagate(script)
    test_zero_skills_aborts(script)

    if failures:
        for message in failures:
            print(f"FAIL  {message}")
        return 1
    print("OK  mirror propagates deletions, skips non-skills, aborts on empty, spares plugin files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
