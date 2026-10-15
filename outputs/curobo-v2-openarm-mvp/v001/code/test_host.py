# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only checks of sampling boundaries and statistical failure accounting."""
import json
from pathlib import Path
import tempfile
import unittest

from summarize import percentile, summarize, wilson


class StatisticsTests(unittest.TestCase):
    def test_all_success_is_not_certainty(self):
        lower, upper = wilson(5, 5)
        self.assertLess(lower, .6)
        self.assertAlmostEqual(upper, 1)
        self.assertIsNone(wilson(0, 0))

    def test_quantiles_accept_empty_and_single_sample(self):
        self.assertIsNone(percentile([], .95))
        self.assertEqual(percentile([3], .95), 3)
        self.assertAlmostEqual(percentile([10, 1, 5], .5), 5)

    def test_startup_failure_does_not_become_zero_task_success_rate(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p / 'launch.json').write_text(json.dumps(dict(backend='v2', status='failed', smoke=False,
                samples=[], foreign_gpu_processes_before=[], pid=123, returncode=1, started_unix=0, ended_unix=1)))
            result = summarize(p)
            self.assertIsNone(result['attempts'])
            self.assertIsNone(result['success_rate'])

    def test_completed_failures_remain_in_denominator_and_cancellations_do_not(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p / 'launch.json').write_text(json.dumps(dict(backend='v1', status='completed', smoke=False,
                samples=[dict(processes=[dict(pid=123, memory_mib=100), dict(pid=456, memory_mib=999)])],
                foreign_gpu_processes_before=[], pid=123, returncode=0, started_unix=0, ended_unix=1)))
            (p / 'episodes.result.json').write_text(json.dumps(dict(num_attempts=2, num_success=1)))
            rows = [dict(event='episode_finished', success=True), dict(event='episode_finished', success=False),
                    dict(event='episode_cancelled', success=None)]
            (p / 'episodes.telemetry.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
            result = summarize(p)
            self.assertEqual(result['success_rate'], .5)
            self.assertEqual(result['process_gpu_peak_mib'], 100)
            self.assertFalse(result['uncontended'])


class TrajectoryTests(unittest.TestCase):
    def test_repeated_points_preserve_endpoints_and_bound_spacing(self):
        import torch
        from trajectory import resample_path
        path = torch.tensor([[0., 0.], [0., 0.], [.3, .4], [.3, .4]], dtype=torch.float32)
        result = resample_path(path, .1)
        torch.testing.assert_close(result[0], path[0])
        torch.testing.assert_close(result[-1], path[-1])
        self.assertTrue(torch.isfinite(result).all())
        self.assertLessEqual(float(torch.linalg.vector_norm(result[1:] - result[:-1], dim=-1).max()), .100001)


class ModelTests(unittest.TestCase):
    def test_conversion_keeps_authored_model_and_passive_joint_constraints(self):
        from model import convert_robot
        source = {'kinematics': {'ee_link': 'left_tool', 'lock_joints': {'right_joint': 1.2},
                                'cspace': {'joint_names': ['left_joint'], 'retract_config': [0.3]}}}
        converted = convert_robot(source)
        self.assertEqual(source['kinematics']['cspace']['retract_config'], [0.3])
        self.assertEqual(converted['kinematics']['lock_joints'], {'right_joint': 1.2})
        converted['kinematics']['lock_joints']['right_joint'] = 0
        self.assertEqual(source['kinematics']['lock_joints']['right_joint'], 1.2)
        self.assertEqual(converted['kinematics']['cspace']['default_joint_position'], [0.3])

    def test_v2_trajectory_selects_active_joints_by_name(self):
        import torch
        from curobo.types import JointState
        state = JointState.from_position(torch.tensor([[0.7, 3.0, 1.0], [0.0, 6.0, 4.0]]),
                                         joint_names=['locked_finger', 'arm_b', 'arm_a'])
        selected = state.reorder(['arm_a', 'arm_b'])
        torch.testing.assert_close(selected.position, torch.tensor([[1.0, 3.0], [4.0, 6.0]]))
        self.assertEqual(selected.joint_names, ['arm_a', 'arm_b'])


if __name__ == '__main__':
    unittest.main()
