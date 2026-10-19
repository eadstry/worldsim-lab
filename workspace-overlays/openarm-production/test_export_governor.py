# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only resource admission, ancestor limits and sampling tests."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from export_governor import GIB, MIB, ResourceGovernor, cgroup_directories, parse_workers


def ample():
    return dict(cpu_sample_ready=True, cpu_capacity=16, free_cpu_cores=12, cpu_reserve_cores=2,
                memory_available_bytes=20 * GIB, memory_reserve_bytes=4 * GIB,
                worker_private_bytes=256 * MIB, task_headroom=100, worker_task_slots=48,
                shared_memory_free_bytes=10 * GIB, disk_free_bytes=100 * GIB,
                io_pressure_percent=0)


class GovernorTests(unittest.TestCase):
    def test_each_resource_can_pause_admission(self):
        cases = [('cpu_sampling', 'cpu_sample_ready', False),
                 ('cpu_capacity', 'cpu_capacity', 3),
                 ('cpu_busy', 'free_cpu_cores', 2),
                 ('memory_reserve', 'memory_available_bytes', 4 * GIB),
                 ('process_slots', 'task_headroom', 47),
                 ('shared_memory', 'shared_memory_free_bytes', 7 * MIB),
                 ('disk_space', 'disk_free_bytes', GIB),
                 ('io_pressure', 'io_pressure_percent', 20)]
        for expected, key, value in cases:
            with self.subTest(resource=expected):
                sample = {**ample(), key: value}
                self.assertEqual(ResourceGovernor.evaluate(sample, 2, GIB), expected)
        self.assertEqual(ResourceGovernor.evaluate(ample(), 2, GIB), 'available')

    def test_container_ancestor_limits_override_host_capacity(self):
        readings = {
            '/proc/stat': 'cpu0 100 0 0 100 0 0 0 0\ncpu1 100 0 0 100 0 0 0 0',
            '/proc/meminfo': f'MemTotal: {64 * GIB // 1024} kB\nMemAvailable: {48 * GIB // 1024} kB',
            '/cg/cpu.max': '200000 100000', '/cg/cpu.stat': 'usage_usec 1000000',
            '/cg/memory.max': str(4 * GIB), '/cg/memory.current': str(3 * GIB),
            '/cg/pids.max': '100', '/cg/pids.current': '60',
            '/cg/child/cpu.max': 'max 100000', '/cg/child/memory.max': 'max',
        }
        governor = ResourceGovernor()
        with patch('export_governor.read', side_effect=lambda p: readings.get(str(p), '')), \
             patch('export_governor.cgroup_directories', return_value=[Path('/cg/child'), Path('/cg')]), \
             patch('export_governor.os.sched_getaffinity', return_value={0, 1}), \
             patch('export_governor.shutil.disk_usage', return_value=SimpleNamespace(free=100 * GIB)), \
             patch('export_governor.time.monotonic', side_effect=[10, 11]):
            first = governor.sample([], Path('/tmp/output'))
            self.assertFalse(first['cpu_sample_ready'])
            readings['/proc/stat'] = 'cpu0 150 0 0 150 0 0 0 0\ncpu1 150 0 0 150 0 0 0 0'
            readings['/cg/cpu.stat'] = 'usage_usec 2800000'
            second = governor.sample([], Path('/tmp/output'))
        self.assertEqual(second['cpu_capacity'], 2)
        self.assertAlmostEqual(second['free_cpu_cores'], .2)
        self.assertEqual(second['memory_capacity_bytes'], 4 * GIB)
        self.assertEqual(second['memory_available_bytes'], GIB)
        self.assertEqual(second['task_headroom'], 40)

    def test_private_memory_estimate_excludes_shared_episode_mapping(self):
        governor = ResourceGovernor()
        import export_governor
        original = export_governor.read

        def values(path):
            if str(path) == '/proc/12345/smaps_rollup':
                return 'Rss: 8000000 kB\nPrivate_Clean: 102400 kB\nPrivate_Dirty: 204800 kB'
            if str(path) == '/proc/12345/status':
                return 'Threads: 4'
            return original(path)

        with patch('export_governor.read', side_effect=values):
            result = governor.sample([SimpleNamespace(pid=12345)], Path('/tmp/output'))
        self.assertEqual(result['worker_private_bytes'], 375 * MIB)

    def test_only_one_admission_per_sampling_interval(self):
        governor = ResourceGovernor()
        with patch.object(governor, 'sample', return_value=ample()) as sample, \
             patch('export_governor.time.monotonic', side_effect=[0, .2, 1.1]):
            args = [], {'0': {'memory_bytes': GIB}}, Path('/tmp/output')
            self.assertTrue(governor.decide(*args)['allow'])
            self.assertIsNone(governor.decide(*args))
            self.assertTrue(governor.decide(*args)['allow'])
            self.assertEqual(sample.call_count, 2)

    def test_missing_resources_pause_instead_of_unbounded_spawn(self):
        governor = ResourceGovernor()
        with patch.object(governor, 'sample', side_effect=OSError('no access')):
            result = governor.decide([], {'0': {'memory_bytes': 100}}, Path('/tmp/output'))
        self.assertFalse(result['allow'])
        self.assertEqual(result['reason'], 'resources_unavailable')

    def test_cgroup_membership_includes_visible_ancestors(self):
        values = {'/proc/self/cgroup': '0::/work/leaf',
                  '/proc/self/mountinfo': '1 0 0:1 / /sys/fs/cgroup ro - cgroup2 none rw'}
        with patch('export_governor.read', side_effect=lambda p: values.get(str(p), '')), \
             patch.object(Path, 'is_dir', return_value=True):
            self.assertEqual(cgroup_directories(), [Path('/sys/fs/cgroup/work/leaf'),
                                                   Path('/sys/fs/cgroup/work'), Path('/sys/fs/cgroup')])

    def test_worker_argument_supports_auto_and_legacy_counts(self):
        self.assertEqual(parse_workers('auto'), 'auto')
        self.assertEqual(parse_workers('0'), 0)
        self.assertEqual(parse_workers('4'), 4)
        for value in ('-1', 'unlimited', '1.5'):
            with self.assertRaises(ValueError):
                parse_workers(value)


if __name__ == '__main__':
    unittest.main()
