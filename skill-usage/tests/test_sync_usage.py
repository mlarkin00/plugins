"""End-to-end sync tests against real git repositories.

The scenario these exist for: four machines sharing one repo. Before sharding,
the second machine to push was rejected, stayed ahead forever, and its counts
never reached anyone — and a manual pull produced a conflict that the next
increment turned into total data loss.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, '../scripts'))
SYNC = os.path.join(SCRIPTS, 'sync-usage.py')
sys.path.insert(0, SCRIPTS)

import usage_lib  # noqa: E402


def git(repo, *args, check=True):
    result = subprocess.run(['git', '-C', repo, *args],
                            capture_output=True, text=True, timeout=30)
    if check and result.returncode != 0:
        raise AssertionError('git %s failed: %s' % (' '.join(args), result.stderr))
    return result


class MultiMachine(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.remote = os.path.join(self.root, 'remote.git')
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', self.remote],
                       check=True)
        self.machines = {}

    def add_machine(self, name):
        """A clone plus its own config/cache dirs, so it gets its own shard."""
        work = os.path.join(self.root, name)
        subprocess.run(['git', 'clone', '-q', self.remote, work],
                       check=True, capture_output=True)
        git(work, 'checkout', '-q', '-B', 'main')
        git(work, 'config', 'user.email', '%s@test' % name)
        git(work, 'config', 'user.name', name)
        env = dict(os.environ)
        env.update({
            'SKILL_USAGE_REPO': work,
            'XDG_CONFIG_HOME': os.path.join(self.root, name + '-config'),
            'XDG_CACHE_HOME': os.path.join(self.root, name + '-cache'),
        })
        env.pop('ACTIVE_SKILLS_USAGE_REPO', None)
        self.machines[name] = (work, env)
        return work

    def seed(self, name):
        """First machine needs an initial commit so clones are not empty."""
        work, _ = self.machines[name]
        with open(os.path.join(work, 'README.md'), 'w') as f:
            f.write('seed\n')
        git(work, 'add', '-A')
        git(work, 'commit', '-qm', 'init')
        git(work, 'push', '-q', '-u', 'origin', 'main')
        git(work, 'branch', '--set-upstream-to=origin/main', check=False)

    def use(self, name, skill):
        _, env = self.machines[name]
        snippet = ("import sys; sys.path.insert(0, %r); import usage_lib\n"
                   "usage_lib.increment(%r)\n" % (SCRIPTS, skill))
        result = subprocess.run([sys.executable, '-c', snippet],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def stamp_path(self, name):
        _, env = self.machines[name]
        return os.path.join(env['XDG_CACHE_HOME'], 'skill-usage', 'last-sync')

    def sync(self, name, *extra):
        """Run a sync and wait for it.

        --foreground keeps the git work in the child we are waiting on. The
        detached default is deliberately raced against the caller, so a test
        asserting on the remote right afterwards would be checking a push that
        has not happened yet; test_detached_default_still_delivers covers that
        path on its own terms.
        """
        _, env = self.machines[name]
        cache = self.stamp_path(name)
        if os.path.exists(cache):
            os.remove(cache)  # each test session should be eligible
        return subprocess.run([sys.executable, SYNC, '--foreground', *extra],
                              env=env, capture_output=True, text=True, timeout=60)

    def remote_head(self):
        return git(self.remote, 'rev-parse', 'main').stdout.strip()

    def remote_totals(self):
        checkout = tempfile.mkdtemp(dir=self.root)
        subprocess.run(['git', 'clone', '-q', self.remote, checkout],
                       check=True, capture_output=True)
        return usage_lib.totals(checkout)

    # --- the tests -----------------------------------------------------

    def test_four_machines_all_reach_the_remote(self):
        names = ['alpha', 'beta', 'gamma', 'delta']
        for name in names:
            self.add_machine(name)
        self.seed('alpha')
        for name in names[1:]:
            git(self.machines[name][0], 'pull', '-q', 'origin', 'main')
            git(self.machines[name][0], 'branch',
                '--set-upstream-to=origin/main', check=False)

        # Every machine uses the same skill, then syncs, without pulling first.
        for name in names:
            self.use(name, 'shared-skill')
            self.use(name, name + '-only')
            result = self.sync(name)
            self.assertEqual(result.returncode, 0, result.stderr)

        totals = self.remote_totals()
        self.assertEqual(totals['shared-skill']['count'], 4,
                         'every machine must contribute; got %r' % (totals,))
        for name in names:
            self.assertEqual(totals[name + '-only']['count'], 1)

        # Four distinct shards, no shared write target.
        checkout = tempfile.mkdtemp(dir=self.root)
        subprocess.run(['git', 'clone', '-q', self.remote, checkout],
                       check=True, capture_output=True)
        shards = os.listdir(os.path.join(checkout, usage_lib.COUNTS_DIRNAME))
        self.assertEqual(len(shards), 4, shards)

    def test_stale_machine_recovers_without_being_pulled_by_hand(self):
        """The original failure: push rejected, branch ahead forever."""
        self.add_machine('one')
        self.add_machine('two')
        self.seed('one')
        git(self.machines['two'][0], 'pull', '-q', 'origin', 'main')
        git(self.machines['two'][0], 'branch',
            '--set-upstream-to=origin/main', check=False)

        self.use('one', 'skill-a')
        self.sync('one')          # one is now ahead of two

        self.use('two', 'skill-b')
        self.sync('two')          # must fetch, rebase, and land anyway

        work, _ = self.machines['two']
        git(work, 'fetch', '-q')
        ahead = git(work, 'rev-list', '--count', 'origin/main..HEAD').stdout.strip()
        self.assertEqual(ahead, '0', 'machine two never delivered its counts')
        self.assertEqual(self.remote_totals()['skill-b']['count'], 1)

    def test_unrelated_local_work_is_never_rebased(self):
        """Delivering a usage count must not rewrite the user's own commits."""
        self.add_machine('one')
        self.add_machine('two')
        self.seed('one')
        git(self.machines['two'][0], 'pull', '-q', 'origin', 'main')
        git(self.machines['two'][0], 'branch',
            '--set-upstream-to=origin/main', check=False)

        self.use('one', 'skill-a')
        self.sync('one')

        work, _ = self.machines['two']
        with open(os.path.join(work, 'my-work.txt'), 'w') as f:
            f.write('important\n')
        git(work, 'add', '-A')
        git(work, 'commit', '-qm', 'my real work')
        mine = git(work, 'rev-parse', 'HEAD').stdout.strip()

        self.use('two', 'skill-b')
        result = self.sync('two')
        self.assertEqual(result.returncode, 0, result.stderr)

        log = git(work, 'log', '--format=%H %s').stdout
        self.assertIn(mine, log, 'the user\'s commit was rewritten')
        self.assertEqual(
            git(work, 'log', '-1', '--format=%s', mine).stdout.strip(),
            'my real work')

    def test_first_sync_commits_an_untracked_shard(self):
        """`git commit --only` refuses a path git has never seen."""
        self.add_machine('solo')
        self.seed('solo')
        self.use('solo', 'skill-a')
        result = self.sync('solo')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.remote_totals()['skill-a']['count'], 1)

    # --- detaching, and the throttle stamp that guards the retry -------

    def git_shim(self, subcommand, seconds=5):
        """A `git` earlier on PATH that hangs on one subcommand.

        Lets a test hold the worker inside the push for a known window without
        depending on a slow network.
        """
        bindir = os.path.join(self.root, 'shim-bin')
        os.makedirs(bindir, exist_ok=True)
        shim = os.path.join(bindir, 'git')
        with open(shim, 'w') as f:
            f.write('#!/bin/sh\n'
                    'for a in "$@"; do\n'
                    '  if [ "$a" = "%s" ]; then sleep %d; exit 0; fi\n'
                    'done\n'
                    'exec %s "$@"\n' % (subcommand, seconds, shutil.which('git')))
        os.chmod(shim, 0o755)
        return bindir

    def env_with_shim(self, name, subcommand, seconds=5):
        _, env = self.machines[name]
        env = dict(env)
        env['PATH'] = (self.git_shim(subcommand, seconds) + os.pathsep + env['PATH'])
        return env

    def await_counts_commit(self, name, timeout=30):
        work, _ = self.machines[name]
        deadline = time.time() + timeout
        while time.time() < deadline:
            subject = git(work, 'log', '-1', '--format=%s').stdout.strip()
            if subject.startswith('chore(active-skills)'):
                return True
            time.sleep(0.05)
        return False

    def test_detached_default_still_delivers(self):
        """The default path does the same work, just not in the caller."""
        self.add_machine('solo')
        self.seed('solo')
        self.use('solo', 'skill-a')
        _, env = self.machines['solo']
        before = self.remote_head()

        result = subprocess.run([sys.executable, SYNC], env=env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

        deadline = time.time() + 30
        while time.time() < deadline and self.remote_head() == before:
            time.sleep(0.05)
        self.assertNotEqual(self.remote_head(), before,
                            'the detached worker never delivered the counts')
        self.assertEqual(self.remote_totals()['skill-a']['count'], 1)

    def test_the_hook_returns_while_the_push_is_still_running(self):
        """The whole point: the caller must not be waiting on the network.

        Run inline this would take the shim's full sleep; detached it returns
        as soon as the worker is spawned.
        """
        self.add_machine('solo')
        self.seed('solo')
        self.use('solo', 'skill-a')
        env = self.env_with_shim('solo', 'push', seconds=5)

        start = time.monotonic()
        result = subprocess.run([sys.executable, SYNC], env=env,
                                capture_output=True, text=True, timeout=60)
        elapsed = time.monotonic() - start

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(elapsed, 3.0,
                        'the hook waited for the push instead of detaching')

    def test_a_worker_killed_during_the_push_leaves_no_stamp(self):
        """Ordering guard for the throttle.

        Stamped before the push, a worker killed mid-push claimed a sync that
        never landed and the throttle then skipped the retry. Claude Code kills
        the hook's whole process group, which is what this reproduces.
        """
        self.add_machine('solo')
        self.seed('solo')
        self.use('solo', 'skill-a')
        stamp = self.stamp_path('solo')
        if os.path.exists(stamp):
            os.remove(stamp)
        env = self.env_with_shim('solo', 'push', seconds=5)

        worker = subprocess.Popen([sys.executable, SYNC, '--foreground'], env=env,
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL,
                                  start_new_session=True)
        try:
            self.assertTrue(self.await_counts_commit('solo'),
                            'worker never reached the push')
            os.killpg(os.getpgid(worker.pid), signal.SIGKILL)
        finally:
            worker.wait(timeout=10)

        self.assertFalse(
            os.path.exists(stamp),
            'a worker killed during the push must not stamp the throttle')

    def test_a_failed_push_still_stamps_the_throttle(self):
        """A clean failure is not the same as a killed worker.

        Withholding the stamp when the remote is simply unreachable would make
        an offline machine commit on every turn, which is what the throttle is
        there to prevent.
        """
        self.add_machine('solo')
        self.seed('solo')
        self.use('solo', 'skill-a')
        work, _ = self.machines['solo']
        git(work, 'remote', 'set-url', 'origin',
            os.path.join(self.root, 'no-such-remote.git'))

        result = self.sync('solo')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.await_counts_commit('solo'),
                        'the counts were never committed locally')
        self.assertTrue(os.path.exists(self.stamp_path('solo')),
                        'an unreachable remote must still stamp the throttle')

    def test_sync_is_a_noop_with_nothing_to_commit(self):
        self.add_machine('solo')
        self.seed('solo')
        before = git(self.machines['solo'][0], 'rev-parse', 'HEAD').stdout
        self.assertEqual(self.sync('solo').returncode, 0)
        self.assertEqual(git(self.machines['solo'][0], 'rev-parse', 'HEAD').stdout,
                         before)


if __name__ == '__main__':
    unittest.main()
