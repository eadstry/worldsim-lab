# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only checks for admission failures that must prevent a production launch."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from preflight import assess, memory_snapshot, required_gib


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.protocol = json.loads(Path(__file__).with_name('protocol.json').read_text())
        self.gpu = {'devices': 'GPU-test, test, 32607, 0', 'compute_pids': []}

    def memory(self, available):
        return {'effective_available_gib': available, 'probe_errors': []}

    def test_current_host_estimate_is_blocked(self):
        self.assertEqual(required_gib(self.protocol), 144)
        result = assess(self.protocol, self.memory(66), self.gpu)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['simulation_executed'])

    def test_fallback_and_observation_reduction_rejected(self):
        changed = copy.deepcopy(self.protocol)
        changed['num_envs'] = 8
        with self.assertRaises(ValueError):
            required_gib(changed)
        for key, value in [('image_shape', [240, 320, 3]), ('keep_failed', False),
                           ('allow_parallelism_fallback', True), ('control_hz', 15)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.protocol)
                changed['configuration'][key] = value
                with self.assertRaises(ValueError):
                    required_gib(changed)

    def test_invalid_memory_budget_rejected(self):
        for value in [-1, 0, float('nan'), float('inf'), True]:
            changed = copy.deepcopy(self.protocol)
            changed['admission']['recorder_gib_per_env'] = value
            with self.assertRaises(ValueError):
                required_gib(changed)

    def test_missing_gpu_or_busy_gpu_blocks(self):
        for gpu in [{'error': 'driver unavailable'},
                    {**self.gpu, 'compute_pids': ['123']}]:
            self.assertEqual(assess(self.protocol, self.memory(160), gpu)['status'], 'blocked')

    def test_adequate_resources_do_not_mean_simulation_passed(self):
        result = assess(self.protocol, self.memory(160), self.gpu)
        self.assertEqual(result['status'], 'resource_admissible')
        self.assertFalse(result['simulation_executed'])

    def test_parent_cgroup_cap_applies_to_unlimited_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc, cg = root / 'proc', root / 'cgroup'
            (proc / 'self').mkdir(parents=True)
            (cg / 'child').mkdir(parents=True)
            (proc / 'meminfo').write_text('MemTotal: 201326592 kB\nMemAvailable: 167772160 kB\n')
            (proc / 'self/cgroup').write_text('0::/child\n')
            (cg / 'child/memory.max').write_text('max')
            (cg / 'memory.max').write_text(str(128 * 1024**3))
            (cg / 'memory.current').write_text(str(32 * 1024**3))
            snapshot = memory_snapshot(proc, cg)
            self.assertEqual(snapshot['effective_available_gib'], 96)
            self.assertFalse(snapshot['probe_errors'])
            self.assertEqual(assess(self.protocol, snapshot, self.gpu)['status'], 'blocked')

    def test_unknown_cgroup_does_not_grant_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'self').mkdir()
            (root / 'meminfo').write_text('MemTotal: 201326592 kB\nMemAvailable: 167772160 kB\n')
            (root / 'self/cgroup').write_text('0::/missing\n')
            snapshot = memory_snapshot(root, root / 'cg')
            self.assertTrue(snapshot['probe_errors'])
            self.assertEqual(assess(self.protocol, snapshot, self.gpu)['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
