#!/usr/bin/env python3
"""Unit tests for poll-repo.py script."""

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "poll-repo.py"
spec = importlib.util.spec_from_file_location("poll_repo", SCRIPT_PATH)
poll_repo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(poll_repo)


class TestPollRepoTodo(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.agents_dir = Path(self.test_dir) / ".agents"
        self.agents_dir.mkdir()
        self.todo_path = self.agents_dir / "TODO.md"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_add_p0_todo_replaces_none(self):
        self.todo_path.write_text(
            "# TODO\n\n## P0 — Address Immediately\n\n(none)\n\n## P1 — Important / Unblocking\n",
            encoding="utf-8",
        )
        msg = "Git sync conflict when polling repository: test conflict"
        poll_repo.add_p0_todo(Path(self.test_dir), msg)
        content = self.todo_path.read_text(encoding="utf-8")
        self.assertIn(f"- [ ] **[P0]** {msg}", content)
        self.assertNotIn("(none)", content)

    def test_add_p0_todo_appends_to_existing(self):
        self.todo_path.write_text(
            "# TODO\n\n## P0 — Address Immediately\n\n- [ ] **[P0]** Existing urgent item\n\n## P1 — Important / Unblocking\n",
            encoding="utf-8",
        )
        msg = "Git sync conflict when polling repository: test conflict"
        poll_repo.add_p0_todo(Path(self.test_dir), msg)
        content = self.todo_path.read_text(encoding="utf-8")
        self.assertIn("- [ ] **[P0]** Existing urgent item", content)
        self.assertIn(f"- [ ] **[P0]** {msg}", content)

    def test_add_p0_todo_no_duplicate(self):
        msg = "Git sync conflict when polling repository: test conflict"
        self.todo_path.write_text(
            f"# TODO\n\n## P0 — Address Immediately\n\n- [ ] **[P0]** {msg}\n\n## P1 — Important / Unblocking\n",
            encoding="utf-8",
        )
        poll_repo.add_p0_todo(Path(self.test_dir), msg)
        content = self.todo_path.read_text(encoding="utf-8")
        self.assertEqual(content.count(msg), 1)

    def test_add_p0_todo_missing_p0_section(self):
        self.todo_path.write_text(
            "# TODO\n\n## P1 — Important / Unblocking\n",
            encoding="utf-8",
        )
        msg = "Git sync conflict when polling repository: test conflict"
        poll_repo.add_p0_todo(Path(self.test_dir), msg)
        content = self.todo_path.read_text(encoding="utf-8")
        self.assertIn("## P0 — Address Immediately", content)
        self.assertIn(f"- [ ] **[P0]** {msg}", content)



class TestPollRepoGit(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.origin_dir = os.path.join(self.test_dir, "origin.git")
        self.local_dir = os.path.join(self.test_dir, "local")
        self.other_dir = os.path.join(self.test_dir, "other")

        # Create bare origin
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", self.origin_dir], check=True, capture_output=True)

        # Clone local
        subprocess.run(["git", "clone", self.origin_dir, self.local_dir], check=True, capture_output=True)
        self._git_config(self.local_dir)

        # Create initial commit in local and push
        init_file = os.path.join(self.local_dir, "README.md")
        with open(init_file, "w", encoding="utf-8") as f:
            f.write("# Init\n")
        subprocess.run(["git", "add", "README.md"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=self.local_dir, check=True, capture_output=True)

        # Clone other to push remote changes
        subprocess.run(["git", "clone", self.origin_dir, self.other_dir], check=True, capture_output=True)
        self._git_config(self.other_dir)

        # Create TODO.md in local
        agents_dir = os.path.join(self.local_dir, ".agents")
        os.makedirs(agents_dir, exist_ok=True)
        self.todo_path = os.path.join(agents_dir, "TODO.md")
        with open(self.todo_path, "w", encoding="utf-8") as f:
            f.write("# TODO\n\n## P0 — Address Immediately\n\n(none)\n\n## P1 — Important / Unblocking\n")
        subprocess.run(["git", "add", ".agents/TODO.md"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Add TODO.md"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "pull"], cwd=self.other_dir, check=True, capture_output=True)

    def _git_config(self, repo_dir):
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_up_to_date(self):
        ret = poll_repo.poll_and_update(cwd=self.local_dir)
        self.assertEqual(ret, 0)

    def test_clean_pull(self):
        # Push commit from other
        remote_file = os.path.join(self.other_dir, "remote.txt")
        with open(remote_file, "w", encoding="utf-8") as f:
            f.write("remote commit\n")
        subprocess.run(["git", "add", "remote.txt"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Add remote.txt"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=self.other_dir, check=True, capture_output=True)

        ret = poll_repo.poll_and_update(cwd=self.local_dir)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.exists(os.path.join(self.local_dir, "remote.txt")))

    def test_dirty_pull(self):
        # Push commit from other
        remote_file = os.path.join(self.other_dir, "remote2.txt")
        with open(remote_file, "w", encoding="utf-8") as f:
            f.write("remote commit 2\n")
        subprocess.run(["git", "add", "remote2.txt"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Add remote2.txt"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=self.other_dir, check=True, capture_output=True)

        # Create dirty uncommitted file in local
        dirty_file = os.path.join(self.local_dir, "dirty.txt")
        with open(dirty_file, "w", encoding="utf-8") as f:
            f.write("local uncommitted work\n")

        ret = poll_repo.poll_and_update(cwd=self.local_dir)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.exists(os.path.join(self.local_dir, "remote2.txt")))
        self.assertTrue(os.path.exists(dirty_file))
        with open(dirty_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "local uncommitted work\n")

    def test_commit_conflict(self):
        # Push conflicting change from other
        conflict_other = os.path.join(self.other_dir, "conflict.txt")
        with open(conflict_other, "w", encoding="utf-8") as f:
            f.write("remote version\n")
        subprocess.run(["git", "add", "conflict.txt"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Remote conflict"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=self.other_dir, check=True, capture_output=True)

        # Create conflicting commit in local (same filename, different content)
        conflict_local = os.path.join(self.local_dir, "conflict.txt")
        with open(conflict_local, "w", encoding="utf-8") as f:
            f.write("local version\n")
        subprocess.run(["git", "add", "conflict.txt"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Local conflict"], cwd=self.local_dir, check=True, capture_output=True)

        ret = poll_repo.poll_and_update(cwd=self.local_dir)
        self.assertEqual(ret, 1)

        # Verify local file still has local version (rebase aborted cleanly)
        with open(conflict_local, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "local version\n")

        # Verify TODO.md has P0 recorded
        with open(self.todo_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("- [ ] **[P0]**", content)
        self.assertNotIn("(none)", content)

    def test_stash_pop_conflict(self):
        # Push conflicting change from other
        conflict_other = os.path.join(self.other_dir, "stash_conflict.txt")
        with open(conflict_other, "w", encoding="utf-8") as f:
            f.write("remote version\n")
        subprocess.run(["git", "add", "stash_conflict.txt"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Remote stash conflict"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=self.other_dir, check=True, capture_output=True)

        # Create uncommitted conflicting file in local
        conflict_local = os.path.join(self.local_dir, "stash_conflict.txt")
        with open(conflict_local, "w", encoding="utf-8") as f:
            f.write("local uncommitted version\n")

        ret = poll_repo.poll_and_update(cwd=self.local_dir)
        self.assertEqual(ret, 1)

        # Verify local file still has local uncommitted version
        with open(conflict_local, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "local uncommitted version\n")

        # Verify TODO.md has P0 recorded
        with open(self.todo_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("- [ ] **[P0]**", content)


if __name__ == "__main__":
    unittest.main()
