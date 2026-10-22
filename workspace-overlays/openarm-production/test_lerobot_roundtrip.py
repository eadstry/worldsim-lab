# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Real official-writer readback; unavailable dependencies are explicit skips."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
from lerobot_direct import DirectWriter
from test_lerobot_direct import fixture


@unittest.skipUnless(importlib.util.find_spec('lerobot'), 'LeRobot is not installed; real v3 readback is blocked')
class OfficialRoundTrip(unittest.TestCase):
    def test_two_episodes_numeric_and_all_video_frames(self):
        import av
        import pyarrow.parquet as pq
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'dataset'
            writer = DirectWriter(output, 'local/direct-test', 'Pick cube', 'openarm')
            for i in range(2):
                arrays, env = fixture()
                arrays['joint_actions'][:] += i
                writer.write(arrays, env, {'success': True}, str(i))
            writer.finish()
            rows = [pq.read_table(p).to_pandas() for p in sorted((output / 'data').rglob('*.parquet'))]
            actual = np.concatenate([np.stack(r['action'].to_numpy()) for r in rows])
            np.testing.assert_array_equal(actual, np.repeat([[42.] * 9, [43.] * 9], 3, axis=0))
            states = np.concatenate([np.stack(r['observation.state'].to_numpy()) for r in rows])
            np.testing.assert_array_equal(states, np.full((6, 9), 7))
            frames = 0
            for path in (output / 'videos').rglob('*.mp4'):
                with av.open(str(path)) as video:
                    for frame in video.decode(video=0):
                        frames += 1
                        self.assertLess(np.abs(frame.to_ndarray(format='rgb24').astype(float) - 50).mean(), 8)
            self.assertEqual(frames, 6)
            dataset = LeRobotDataset('local/direct-test', root=output, video_backend='torchcodec')
            for i in (0, 2, 3, 5):
                np.testing.assert_array_equal(dataset[i]['action'].numpy(), np.full(9, 42 + i // 3))
            self.assertFalse(list(output.rglob('*.hdf5')))
