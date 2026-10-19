# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only tests for acceptance, rate denominators and comparison completeness."""
import tempfile
import unittest
from pathlib import Path

from bench32 import aggregate, summarize, write
import json


class AcceptanceTests(unittest.TestCase):
    def fixture(self, root, count=34):
        output = root / 'dataset.hdf5'
        output.write_bytes(b'fixture, not an HDF5 dataset')
        write(output.with_suffix('.run.json'), {'status': 'succeeded'})
        write(output.with_suffix('.result.json'), dict(requested_trials=32, num_success=count, num_attempts=count + 1))
        write(output.with_suffix('.validation.json'), dict(passed=True, sha256='fixture', episodes=[
            dict(recorded_success=True, final_state_success=True, steps=1400) for _ in range(count)]))
        events = [dict(event='generation_policy', guarantee_success=True),
                  dict(event='episode_started', elapsed_seconds=10, time_utc='2026-10-14T00:00:10+00:00')]
        events += [dict(event='episode_finished', success=True, elapsed_seconds=11 + i) for i in range(count)]
        events += [dict(event='output_ready', elapsed_seconds=60, time_utc='2026-10-14T00:01:00+00:00')]
        output.with_suffix('.telemetry.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        return output

    def test_overshoot_is_not_credited_and_validation_is_timed(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = summarize(self.fixture(Path(tmp)), 32, 70, 10)
        self.assertEqual(row['overshoot'], 2)
        self.assertEqual(row['verified_seconds'], 80)
        self.assertEqual(row['episodes_per_minute'], 24)
        self.assertEqual(row['final_ready_per_minute'], 38.4)
        self.assertIsNone(row['gpu_util_mean'])

    def test_interrupted_or_incomplete_export_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = self.fixture(Path(tmp))
            write(output.with_suffix('.run.json'), {'status': 'interrupted'})
            with self.assertRaises(ValueError):
                summarize(output, 32, 70, 10)
            write(output.with_suffix('.run.json'), {'status': 'succeeded'})
            write(output.with_suffix('.export.json'), {'status': 'starting'})
            with self.assertRaises(ValueError):
                summarize(output, 32, 70, 10)

    def test_missing_saved_or_failed_terminal_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = self.fixture(Path(tmp), count=31)
            with self.assertRaises(ValueError):
                summarize(output, 32, 70, 10)
            output = self.fixture(Path(tmp))
            path = output.with_suffix('.validation.json')
            data = json.loads(path.read_text())
            data['episodes'][0]['final_state_success'] = False
            write(path, data)
            with self.assertRaises(ValueError):
                summarize(output, 32, 70, 10)

    def test_partial_repeats_cannot_produce_speedup(self):
        rows = [dict(variant='sync', num_envs=8, status='valid', episodes_per_minute=2, gpu_util_mean=50),
                dict(variant='auto', num_envs=8, status='valid', episodes_per_minute=4, gpu_util_mean=80)]
        report = aggregate(rows, 'sync', repeats=3)
        self.assertFalse(report['best_by_variant'])
        self.assertTrue(all(s['matched_parallelism_speedup'] is None for s in report['cells']))
        report = aggregate(rows, 'sync', repeats=1)
        self.assertEqual(report['best_by_variant']['auto']['best_parallelism_speedup'], 2)
        self.assertEqual(report['cells'][1]['matched_parallelism_speedup'], 2)


if __name__ == '__main__':
    unittest.main()
