# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
import subprocess
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import benchmark_parallel

class SamplingTests(unittest.TestCase):
    def test_worker_stops_child_if_independent_sampler_stalls(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'worker'
            output.mkdir()
            sample = root / 'gpu.jsonl'
            sample.touch()
            os.utime(sample, (time.time() - 30, time.time() - 30))
            with patch('benchmark_parallel.os.sched_setaffinity'), patch('benchmark_parallel.subprocess.Popen') as launch, patch('benchmark_parallel.stop_tree') as stop:
                launch.return_value.pid = 123
                launch.return_value.poll.return_value = None
                with self.assertRaises(TimeoutError):
                    benchmark_parallel.worker(['unused'], output, [0], 300, root / 'STOP', os.getpid())
                stop.assert_called_once_with(123)
            self.assertTrue((root / 'STOP').exists())
            self.assertTrue((output / 'watchdog-stop.json').exists())

    def test_physical_core_allocation_balances_hybrid_cpu(self):
        def topology(path):
            if path.name == 'physical_package_id': return '0'
            cpu = int(path.parts[-3].removeprefix('cpu'))
            return str(cpu // 2 if cpu < 16 else cpu - 8)
        with patch('pathlib.Path.read_text', topology):
            groups = benchmark_parallel.cpu_partitions(list(range(24)), 2)
        self.assertEqual([len(g) for g in groups], [12, 12])
        self.assertEqual(sorted(groups[0] + groups[1]), list(range(24)))
        for group in groups:
            self.assertEqual(sum(c < 16 for c in group), 8)
            for cpu in group:
                if cpu < 16: self.assertIn(cpu ^ 1, group)

    def test_timeout_is_missing_not_zero_load_or_run_failure(self):
        with patch('benchmark_parallel.subprocess.run', side_effect=subprocess.TimeoutExpired('nvidia-smi', 5)):
            sample = benchmark_parallel.gpu_sample()
        self.assertIsNone(sample['returncode'])
        self.assertEqual(sample['csv'], '')
        self.assertIn('timeout', sample['error'])
        self.assertGreater(sample['available_ram_bytes'], 0)

if __name__ == '__main__': unittest.main()
