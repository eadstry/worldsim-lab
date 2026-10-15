"""Integration tests use real Linux processes, locks and an isolated queue."""

import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'task-queue.py'


class TaskQueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.queue = self.root / 'queue'
        self.workers = []

    def tearDown(self):
        for worker in self.workers:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()
        self.temporary.cleanup()

    def command(self, *args):
        return [sys.executable, str(SCRIPT), '--queue-dir', str(self.queue), *args]

    def cli(self, *args, env=None, check=True):
        return subprocess.run(self.command(*args), capture_output=True, text=True,
                              env=env, check=check, timeout=15)

    def submit(self, code, *, cwd=None, env=None, timeout=None, auto=False):
        args = ['submit', '--cwd', str(cwd or self.root)]
        if not auto:
            args.append('--no-start')
        if timeout:
            args.extend(['--timeout', str(timeout)])
        args.extend(['--', sys.executable, '-c', code])
        return int(self.cli(*args, env=env).stdout)

    def worker(self):
        worker = subprocess.Popen(self.command('worker'), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
        self.workers.append(worker)
        return worker

    def rows(self):
        with sqlite3.connect(self.queue / 'queue.sqlite3') as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute('SELECT * FROM tasks ORDER BY id')]

    def await_condition(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.03)
        self.fail('Condition not reached before deadline')

    def join_worker(self, worker):
        stdout, stderr = worker.communicate(timeout=15)
        self.assertEqual(worker.returncode, 0, stdout + stderr)

    def test_concurrent_submitters_and_workers_preserve_fifo_without_overlap(self):
        trace = self.root / 'trace.jsonl'
        active = self.root / 'active'

        def submit(index):
            code = f'''import json, os, time
from pathlib import Path
active = Path({str(active)!r})
active.mkdir()
with open({str(trace)!r}, 'a') as f:
    f.write(json.dumps(['start', {index}]) + '\\n')
time.sleep(.1)
with open({str(trace)!r}, 'a') as f:
    f.write(json.dumps(['end', {index}]) + '\\n')
active.rmdir()
'''
            return self.submit(code, auto=True), index

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            submissions = list(pool.map(submit, range(6)))
        workers = [self.worker() for _ in range(3)]
        for worker in workers:
            self.join_worker(worker)
        self.assertTrue(all(row['status'] == 'succeeded' for row in self.rows()))
        expected = [[phase, index] for _, index in sorted(submissions)
                    for phase in ('start', 'end')]
        self.assertEqual([json.loads(line) for line in trace.read_text().splitlines()], expected)

    def test_cwd_environment_and_argument_boundaries_are_per_submission(self):
        for index in range(2):
            cwd = self.root / str(index)
            cwd.mkdir()
            env = dict(os.environ, QUEUE_TEST_VALUE=f'value {index}')
            code = "import os; from pathlib import Path; Path('result').write_text(os.environ['QUEUE_TEST_VALUE']); print(os.getcwd())"
            self.submit(code, cwd=cwd, env=env)
        self.join_worker(self.worker())
        for index in range(2):
            self.assertEqual((self.root / str(index) / 'result').read_text(), f'value {index}')
            self.assertIn(str(self.root / str(index)), self.cli('logs', str(index + 1)).stdout)
        self.assertNotIn('environment', json.loads(self.cli('show', '1').stdout))
        self.assertEqual(self.queue.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.queue / 'queue.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_real_git_worktrees_record_their_own_revision_and_dirty_state(self):
        repo = self.root / 'repo'
        other = self.root / 'other'

        def git(*args):
            return subprocess.run(['git', '-C', str(repo), *args], check=True,
                                  capture_output=True, text=True, timeout=10).stdout.strip()

        repo.mkdir()
        git('init')
        git('-c', 'user.name=Queue Test', '-c', 'user.email=queue@example.invalid',
            'commit', '--allow-empty', '-m', 'Initial')
        first = git('rev-parse', 'HEAD')
        git('worktree', 'add', '-b', 'other', str(other))
        git('-c', 'user.name=Queue Test', '-c', 'user.email=queue@example.invalid',
            'commit', '--allow-empty', '-m', 'Next')
        second = git('rev-parse', 'HEAD')
        (other / 'dirty.txt').write_text('uncommitted')
        self.submit('print("repo")', cwd=repo)
        self.submit('print("other")', cwd=other)
        self.join_worker(self.worker())
        self.assertEqual([(row['revision'], row['dirty']) for row in self.rows()],
                         [(second, 0), (first, 1)])

    def test_failure_missing_executable_and_cancel_do_not_block_next_task(self):
        failed = self.submit('raise SystemExit(7)')
        cancelled = self.submit('raise AssertionError("must not execute")')
        self.cli('cancel', str(cancelled))
        missing = int(self.cli('submit', '--no-start', '--', str(self.root / 'absent')).stdout)
        succeeded = self.submit('print("next task")')
        self.join_worker(self.worker())
        rows = {row['id']: row for row in self.rows()}
        self.assertEqual(rows[failed]['returncode'], 7)
        self.assertEqual(rows[cancelled]['status'], 'cancelled')
        self.assertEqual(rows[missing]['status'], 'failed')
        self.assertIn('FileNotFoundError', rows[missing]['error'])
        self.assertEqual(rows[succeeded]['status'], 'succeeded')
        self.assertEqual(self.cli('wait', str(failed), check=False).returncode, 1)
        self.assertEqual(self.cli('wait', str(succeeded)).returncode, 0)
        self.assertNotEqual(self.cli('cancel', str(succeeded), check=False).returncode, 0)

    def test_timeout_cleans_descendants_and_continues(self):
        pid_file = self.root / 'descendant.pid'
        descendant = ("import os, signal, time; from pathlib import Path; "
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                      f"Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(30)")
        code = (f'import subprocess, sys, time; subprocess.Popen([sys.executable, "-c", {descendant!r}]); '
                'time.sleep(30)')
        self.submit(code, timeout=.7)
        self.submit('print("after timeout")')
        self.join_worker(self.worker())
        self.assertEqual([row['status'] for row in self.rows()], ['timed_out', 'succeeded'])
        pid = int(pid_file.read_text())
        status_file = Path(f'/proc/{pid}/stat')
        self.await_condition(lambda: not status_file.exists() or
                             status_file.read_text().rsplit(')', 1)[1].split()[0] == 'Z')

    def test_crashed_worker_keeps_slot_until_child_exits_without_retry(self):
        active = self.root / 'child-active'
        code = (f'from pathlib import Path; import time; p=Path({str(active)!r}); '
                'p.touch(); time.sleep(1.2); p.unlink()')
        self.submit(code)
        self.submit(f'from pathlib import Path; assert not Path({str(active)!r}).exists()')
        worker = self.worker()
        self.await_condition(active.exists)
        worker.kill()
        worker.communicate(timeout=5)
        self.join_worker(self.worker())
        self.assertEqual([row['status'] for row in self.rows()], ['interrupted', 'succeeded'])

    def test_automatic_dispatch_finishes_without_manual_worker(self):
        task = self.submit('print("automatic")', auto=True)
        self.await_condition(lambda: self.rows()[0]['status'] == 'succeeded')
        self.assertEqual(self.cli('wait', str(task)).stdout.strip(), 'succeeded')
        self.assertIn('automatic', self.cli('logs', str(task)).stdout)

    def test_sigterm_cleans_running_command_and_leaves_queue_for_restart(self):
        active = self.root / 'started'
        self.submit(f'from pathlib import Path; import time; Path({str(active)!r}).touch(); time.sleep(30)')
        self.submit('print("restart")')
        worker = self.worker()
        self.await_condition(active.exists)
        child_pid = self.rows()[0]['pid']
        worker.terminate()
        worker.communicate(timeout=5)
        self.assertEqual(self.rows()[0]['status'], 'interrupted')
        self.assertFalse(Path(f'/proc/{child_pid}').exists())
        self.join_worker(self.worker())
        self.assertEqual(self.rows()[1]['status'], 'succeeded')


if __name__ == '__main__':
    unittest.main()
