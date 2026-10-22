# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host tests: semantic alignment, fail-closed schemas and direct-writer ownership."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from lerobot_direct import DirectWriter, flatten, schema


def fixture():
    names = [f'joint_{i}' for i in range(9)]
    arrays = {
        'actions': np.zeros((3, 7), np.float32),
        'joint_actions': np.full((3, 9), 42, np.float32),
        'joint_applied_targets': np.full((3, 9), 21, np.float32),
        'obs/joint_pos_absolute': np.full((3, 9), 7, np.float32),
        'obs/camera_rgb': np.full((3, 16, 16, 3), 50, np.uint8),
    }
    fields = {p: dict(names=names, units=['rad'] * 9) for p in arrays if 'rgb' not in p}
    fields['actions'] = dict(names=[f'tcp_{i}' for i in range(7)], units=['1'] * 7)
    fields['joint_actions']['representation'] = 'absolute_joint_position_target'
    return arrays, dict(semantic_metadata=dict(schema_version=1, control_dt=1/30,
        fields=fields, joint_control=dict(names=names)))


class DirectTests(unittest.TestCase):
    def test_pre_step_state_not_substituted_for_command(self):
        arrays, env = fixture()
        count, fps, mapping, features = schema(arrays, env)
        self.assertEqual((count, fps), (3, 30))
        self.assertEqual(features['action'], features['observation.state'])
        np.testing.assert_array_equal(arrays[mapping['action']], 42)
        np.testing.assert_array_equal(arrays[mapping['observation.state']], 7)

    def test_bad_lengths_names_units_finiteness_and_targets_rejected(self):
        for fault in ('length', 'names', 'units', 'nan', 'missing', 'fps'):
            with self.subTest(fault=fault):
                arrays, env = fixture()
                if fault == 'length': arrays['obs/camera_rgb'] = arrays['obs/camera_rgb'][:-1]
                if fault == 'names': env['semantic_metadata']['fields']['obs/joint_pos_absolute']['names'] = ['wrong'] * 9
                if fault == 'units': env['semantic_metadata']['fields']['joint_actions']['units'] = ['m'] * 9
                if fault == 'nan': arrays['joint_actions'][0, 0] = np.nan
                if fault == 'missing': del arrays['joint_actions']
                if fault == 'fps': env['semantic_metadata']['control_dt'] = 0.031
                with self.assertRaises((ValueError, KeyError)): schema(arrays, env)

    def test_flatten_list_frames(self):
        frames = [np.zeros((2, 3), np.uint8), np.ones((2, 3), np.uint8)]
        actual = flatten({'obs': {'rgb': frames}})['obs/rgb']
        frames[0][:] = 9
        self.assertEqual(actual.shape, (2, 2, 3))
        self.assertEqual(actual[0, 0, 0], 0)

    def test_direct_writer_calls_official_api_without_hdf5(self):
        class FakeDataset:
            @classmethod
            def create(cls, *, root, vcodec, **kwargs):
                assert vcodec == 'h264'
                cls.instance = cls()
                cls.instance.root = root
                cls.instance.frames = []
                cls.instance.saved = 0
                cls.instance.image_writer = SimpleNamespace(wait_until_done=lambda: None)
                return cls.instance
            def add_frame(self, frame): self.frames.append(frame)
            def save_episode(self, **kwargs): self.saved += 1
            def stop_image_writer(self): pass
            def finalize(self):
                (self.root / 'meta').mkdir(parents=True)
                (self.root / 'meta/info.json').write_text(json.dumps({'codebase_version': 'v3.0'}))
        modules = {'lerobot': SimpleNamespace(), 'lerobot.datasets': SimpleNamespace(),
                   'lerobot.datasets.lerobot_dataset': SimpleNamespace(LeRobotDataset=FakeDataset)}
        with tempfile.TemporaryDirectory() as folder, patch.dict('sys.modules', modules):
            writer = DirectWriter(Path(folder) / 'dataset', 'local/test', 'test task', 'openarm')
            arrays, env = fixture()
            writer.write(arrays, env, {'success': True}, '0')
            arrays['joint_actions'][:] = 100
            np.testing.assert_array_equal(FakeDataset.instance.frames[0]['action'], 42)
            self.assertEqual(FakeDataset.instance.saved, 1)
            with self.assertRaises(ValueError): writer.write(arrays, env, {'success': False}, '1')
            changed = copy.deepcopy(env)
            changed['semantic_metadata']['control_dt'] = 1 / 60
            with self.assertRaises(ValueError): writer.write(arrays, changed, {'success': True}, '2')
            writer.finish()
            self.assertEqual(list(Path(folder).rglob('*.hdf5')), [])
            self.assertTrue((Path(folder) / 'dataset/production.json').is_file())


if __name__ == '__main__':
    unittest.main()
