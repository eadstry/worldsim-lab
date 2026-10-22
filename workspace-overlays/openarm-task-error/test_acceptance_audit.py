# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
import unittest
import numpy as np
from audit_acceptance import audit_trial, quaternion_speed


def fixture():
    n=40
    pos=np.zeros((n,3));pos[1:,2]=.04
    action=np.zeros((n,7));action[:,-1]=1
    post=np.zeros((n,9));post[:,7:]=.7
    return dict(cube_position=pos,cube_quaternion=np.tile([0.,0.,0.,1.],(n,1)),
                cube_velocity=np.zeros((n,3)),cube_angular_velocity=np.zeros((n,3)),
                source_action=action,post=post,phase=np.full(n,3),
                placed=np.ones(n,dtype=bool),geometry_placed=np.ones(n,dtype=bool))


class AuditTests(unittest.TestCase):
    def test_stationary_pose_and_nonzero_velocity_are_reported_separately(self):
        a=fixture();a['placed'][:]=False;a['cube_velocity'][:,0]=.4
        r=audit_trial(a)
        self.assertFalse(r['original_pass']);self.assertTrue(r['pose_stability_pass'])
        self.assertAlmostEqual(r['last_second_reported_linear_median_m_s'],.4)
        self.assertEqual(r['last_second_derived_linear_median_m_s'],0)

    def test_alternative_requires_geometry_lift_release_and_motion_stability(self):
        a=fixture();a['geometry_placed'][:]=False
        self.assertFalse(audit_trial(a)['pose_stability_pass'])
        a=fixture();a['cube_position'][:,0]=np.arange(40)*.01
        self.assertFalse(audit_trial(a)['pose_stability_pass'])
        a=fixture();a['cube_position'][:,2]=0
        self.assertFalse(audit_trial(a)['pose_stability_pass'])
        a=fixture();a['source_action'][:,-1]=-1
        self.assertFalse(audit_trial(a)['pose_stability_pass'])

    def test_original_stop_can_censor_the_independent_hold_window(self):
        a=fixture()
        for key in a: a[key]=a[key][:16]
        a['geometry_placed'][0]=False
        # The first stable geometry frame still has a position transition.
        # Fifteen original accepted frames need not supply fifteen derived-speed frames.
        r=audit_trial(a)
        self.assertTrue(r['original_pass'])
        self.assertFalse(r['pose_stability_pass'])
        self.assertEqual(r['pose_stability_status'],'not_confirmed_before_original_stop')

    def test_quaternion_sign_does_not_create_spurious_rotation(self):
        q=np.tile([0.,0.,0.,1.],(4,1));q[::2]*=-1
        np.testing.assert_allclose(quaternion_speed(q,1/30),0)


if __name__=='__main__':
    unittest.main()
