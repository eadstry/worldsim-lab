"""CPU processes exercise parallel admission, failures and cleanup without simulation."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'parallel-environments.py'


class ParallelEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
        self.temp.cleanup()

    def start(self, codes, *options, env=None, pass_fds=()):
        jobs = [dict(name=f'env-{i}', cwd=str(self.root), argv=[sys.executable, '-c', code] if isinstance(code, str) else code)
                for i, code in enumerate(codes)]
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'jobs': jobs}))
        process = subprocess.Popen([sys.executable, str(SCRIPT), '--manifest', str(manifest),
                                    '--output', str(self.root / 'output'), '--interval', '.03',
                                    *options], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env=env, pass_fds=pass_fds)
        self.processes.append(process)
        return process

    def wait_for(self, predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.02)
        self.fail('Condition not reached')

    def report(self):
        return json.loads((self.root / 'output/report.json').read_text())

    def test_four_independent_environments_overlap_with_isolated_logs(self):
        code = "import os,time; from pathlib import Path; Path(str(os.getpid())).touch(); time.sleep(.3); print('done')"
        process = self.start([code] * 4, '--workers', '4')
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        report = self.report()
        self.assertEqual(len(report['jobs']), 4)
        self.assertLess(max(j['started'] for j in report['jobs']),
                        min(j['finished'] for j in report['jobs']))
        self.assertEqual(len(list(self.root.glob('[0-9]*'))), 4)
        self.assertTrue(all(p.read_text() == 'done\n' for p in (self.root / 'output').glob('*.log')))

    def test_failure_is_preserved_and_other_work_still_completes(self):
        process = self.start(['raise SystemExit(7)', 'print("valid")'], '--workers', '1')
        process.communicate(timeout=10)
        self.assertEqual(process.returncode, 1)
        self.assertEqual([j['status'] for j in self.report()['jobs']], ['failed', 'succeeded'])

    def test_missing_executable_does_not_cancel_other_environments(self):
        process = self.start([[str(self.root / 'missing-executable')], 'print("valid")'], '--workers', '1')
        process.communicate(timeout=10)
        self.assertEqual(process.returncode, 1)
        self.assertEqual([j['status'] for j in self.report()['jobs']], ['failed_to_start', 'succeeded'])

    def test_timeout_cleans_ignoring_descendant(self):
        descendant = "import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('child').write_text(str(os.getpid()));time.sleep(30)"
        code = f'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",{descendant!r}]);time.sleep(30)'
        process = self.start([code], '--job-timeout', '.5')
        process.communicate(timeout=10)
        self.assertEqual(self.report()['jobs'][0]['status'], 'timed_out')
        path = Path('/proc') / (self.root / 'child').read_text() / 'stat'
        self.wait_for(lambda: not path.exists() or path.read_text().rsplit(')', 1)[1].split()[0] == 'Z')

    def test_gpu_peak_estimate_caps_workers_before_allocations_appear(self):
        fake = self.root / 'nvidia-smi'
        fake.write_text('#!/bin/sh\necho "20, 3000, 32607"\n')
        fake.chmod(0o700)
        env = dict(os.environ, PATH=str(self.root) + ':' + os.environ['PATH'])
        process = self.start(['import time;time.sleep(.2)'] * 6,
                             '--gpu-monitor', '--workers', '16', env=env)
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        report = self.report()
        self.assertEqual(report['effective_workers'], 4)
        self.assertLessEqual(max(s['active'] for s in report['samples']), 4)

    def test_explicit_kit_thread_budget_and_cpu_budget_reach_child(self):
        code = ("import sys,os;"
                "assert len(sys.argv)==2;"
                "assert sys.argv[1]=='--kit_args=--/plugins/carb.tasking.plugin/threadCount=4 --/plugins/omni.tbb.globalcontrol/maxThreadCount=4';"
                "assert all(os.environ[k]=='2' for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'])")
        process = self.start([code], '--kit-threads', '4', '--cpu-threads', '2')
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(self.report()['jobs'][0]['status'], 'succeeded')

    def test_crashed_supervisor_children_keep_shared_queue_lock(self):
        import fcntl
        lock_path = self.root / 'worker.lock'
        with lock_path.open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            code = "import time;from pathlib import Path;Path('started').touch();time.sleep(.8)"
            process = self.start([code], pass_fds=(lock.fileno(),))
            self.wait_for(lambda: (self.root / 'started').exists())
            process.kill()
            process.communicate(timeout=5)
            lock.close()
            with lock_path.open('w') as contender:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                time.sleep(1)
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_termination_of_ignoring_workers_fits_queue_cleanup_deadline(self):
        code = ("import os,signal,time;from pathlib import Path;"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                "Path('pid-'+str(os.getpid())).touch();time.sleep(30)")
        process = self.start([code] * 4, '--workers', '4')
        self.wait_for(lambda: len(list(self.root.glob('pid-*'))) == 4)
        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=10)
        self.assertLess(time.monotonic() - started, 1.8)
        self.assertTrue(all(not Path('/proc', p.name.removeprefix('pid-')).exists()
                            for p in self.root.glob('pid-*')))

    def test_termination_cleans_all_running_environments(self):
        code = "import os,time;from pathlib import Path;Path('pid-'+str(os.getpid())).touch();time.sleep(30)"
        process = self.start([code] * 4, '--workers', '4')
        self.wait_for(lambda: len(list(self.root.glob('pid-*'))) == 4)
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=10)
        self.assertEqual(process.returncode, 143)
        self.assertTrue(all(j['status'] == 'interrupted' for j in self.report()['jobs']))
        self.assertTrue(all(not Path('/proc', p.name.removeprefix('pid-')).exists()
                            for p in self.root.glob('pid-*')))
