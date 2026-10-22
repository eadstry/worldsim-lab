# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Check task acceptance and failure-retaining metric semantics without a simulator."""
import unittest
import numpy as np
from metrics import stable_success, summarize


class AcceptanceTests(unittest.TestCase):
    def test_success_requires_lift_both_open_and_uninterrupted_hold(self):
        placed = np.array([True, True, True])
        lifted = np.array([True, False, True])
        fingers = np.array([[.5, .5], [.5, .5], [.5, .2]])
        count, success = stable_success(placed, lifted, fingers, np.array([14, 14, 14]), 15)
        np.testing.assert_equal(success, [True, False, False])
        np.testing.assert_equal(count, [15, 0, 0])
        count, success = stable_success([False], [True], np.array([[.5, .5]]), count[:1], 15)
        self.assertEqual(count[0], 0)
        self.assertFalse(success[0])

    def test_arm_metrics_exclude_fingers_and_do_not_mix_recording_phases(self):
        a = np.zeros((2, 9)); a[:, :7] = np.pi/180
        a[:, 7:] = 100
        q = np.zeros_like(a)
        result = summarize(dict(request=a, pre=q, post=a/2, applied=a,
                                phase=np.array([0, 3]), ee_error_m=np.zeros(2)), 1/30)
        self.assertAlmostEqual(result['request_pre']['mae_deg'], 1)
        self.assertAlmostEqual(result['request_post']['mae_deg'], .5)
        self.assertIsNone(result['phases']['transport']['mae_deg'])
        self.assertEqual(result['phases']['grasp_lift']['frames'], 0)
        self.assertAlmostEqual(result['duration_s'], 2/30)


if __name__ == '__main__':
    unittest.main()
