# SPDX-License-Identifier: Apache-2.0
"""Verify failed samples remain visible and exported frames are complete."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import h5py
import numpy as np


class AnalysisTests(unittest.TestCase):
    def test_failed_episode_is_retained_with_complete_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plans = []
            for name, success, brightness in [('baseline', True, 80), ('camera', False, 120), ('visual_only', True, 140)]:
                folder = root / 'runs' / name
                folder.mkdir(parents=True)
                plan = dict(name=name, generation_seed=1, randomization_seed=100, active=[], sampled={})
                if name == 'visual_only':
                    plan['sampled'] = {'camera': {'focal_scale': 1.0}}
                path = root / (name + '.json')
                path.write_text(json.dumps(plan))
                plans.append(str(path))
                for label in ('resolved', 'readback'):
                    values = {'camera_intrinsics': [[10, 0, 16], [0, 10, 12], [0, 0, 1]]} if label == 'readback' else {}
                    (folder / f'dr-{label}.json').write_text(json.dumps(values))
                with h5py.File(folder / 'episodes.hdf5', 'w') as f:
                    data = f.create_group('data')
                    data.attrs['env_args'] = json.dumps({'sim_args': {'dt': .005, 'decimation': 4}})
                    e = data.create_group('demo_0')
                    e.attrs['success'] = success
                    e.create_dataset('actions', data=np.zeros((5, 2), dtype=np.float32))
                    e.create_dataset('dr_success_observed', data=[False, False, success, success, success])
                    frames = np.full((5, 24, 32, 3), brightness, dtype=np.uint8)
                    e.create_dataset('overview_rgb', data=frames)
                    e.create_dataset('camera_obs/robot_head_cam_rgb', data=frames)
                    e.create_dataset('initial_state/rigid_object/brown_box/root_pose', data=np.zeros((1, 7)))
                    e.create_dataset('states/rigid_object/brown_box/root_velocity', data=np.zeros((5, 6)))
            (root / 'plans.json').write_text(json.dumps(plans))
            script = Path(__file__).with_name('analyze.py')
            subprocess.run([sys.executable, str(script), '--plans', str(root / 'plans.json'),
                            '--runs', str(root / 'runs'), '--output', str(root / 'analysis')],
                           check=True, capture_output=True)
            result = json.loads((root / 'analysis/summary.json').read_text())
            self.assertEqual(result['num_attempts'], 3)
            self.assertEqual(result['num_success'], 2)
            failed = result['episodes'][1]
            self.assertEqual(result['episodes'][2]['head_video']['decoded_frames'], 5)
            self.assertFalse(failed['success'])
            self.assertEqual(failed['overview_video']['decoded_frames'], 5)
            self.assertEqual(failed['head_video']['decoded_frames'], 5)
            self.assertIsNone(failed['first_recorded_success_step'])
            self.assertAlmostEqual(failed['matched_step_rgb_mae_255']['head'], 40.0)


if __name__ == '__main__':
    unittest.main()
