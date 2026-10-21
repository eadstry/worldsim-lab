# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Ensure final batch telemetry cannot be mistaken for early-completed task data."""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from audit_physics_steps import audit


class PhysicsAuditTest(unittest.TestCase):
    def test_only_timeout_window_is_interpreted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); batch=root/'default';batch.mkdir()
            (batch/'complete.json').write_text('{}')
            (batch/'diagnostic-integration.json').write_text('{}')
            (batch/'trials.json').write_text(json.dumps([
                dict(variant='baseline',demo='demo_0',repeat=0,end_reason='success'),
                dict(variant='kd_half',demo='demo_1',repeat=0,end_reason='timeout')]))
            x=np.zeros((241,2,13));x[:,:,6]=1
            x[:,1,7]=.4
            x[:,0,0]=np.arange(len(x)) # early-completed background must be excluded
            np.savez(batch/'cube-physics-r0.npz',values=x,physics_dt=1/240,
                     assignments=np.array([['baseline','demo_0'],['kd_half','demo_1']]))
            result=audit(root)
            self.assertEqual(len(result['timeout_trials']),1)
            row=result['timeout_trials'][0]
            self.assertEqual(row['demo'],'demo_1')
            self.assertEqual(row['derived_linear_max_m_s'],0)
            self.assertEqual(row['reported_linear_median_m_s'],.4)
            self.assertEqual(row['samples'],240)


if __name__=='__main__': unittest.main()
