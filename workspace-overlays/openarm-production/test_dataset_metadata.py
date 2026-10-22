# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""CPU mocks of resolved managers plus real HDF5 sync/async metadata persistence."""
import ast
import copy
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import h5py
import numpy as np

from dataset_metadata import attach, collect
from export_pool import ExportPool


def environment():
    # Deliberately not alphabetic, left-then-right, or actuator configuration order.
    names = [f'openarm_{side}_joint{i}' for i in range(1, 8) for side in ('right', 'left')]
    names += [f'openarm_{side}_finger_joint{i}' for side in ('right', 'left') for i in (2, 1)]

    class Robot:
        joint_names = names
        data = NS(default_joint_pos=np.tile(np.arange(18, dtype=float), (2, 1)),
                  default_joint_vel=np.zeros((2, 18)))

        def find_joints(self, patterns, preserve_order=False):
            ids = [i for i, name in enumerate(names) if any(re.fullmatch(p, name) for p in patterns)]
            if preserve_order:
                ids = [names.index(p) for p in patterns]
            return ids, [names[i] for i in ids]

    robot = Robot()
    pose = NS(action_dim=6, processed_actions=np.zeros((2, 6)),
              _joint_ids=[i for i, n in enumerate(names) if n.startswith('openarm_left_joint')],
              cfg=NS(scale=(.02, .02, .02, .1, .1, .1), controller=NS(use_relative_mode=True, command_type='pose')))
    fingers = [names.index(f'openarm_left_finger_joint{i}') for i in (2, 1)]
    gripper = NS(action_dim=1, processed_actions=np.zeros((2, 2)), _joint_ids=fingers,
                 cfg=NS(open_command_expr={names[i]: .7 for i in fingers}, close_command_expr={names[i]: 0 for i in fingers}))
    terms = {'left_arm_action': pose, 'left_gripper_action': gripper}
    obs = [('joint_pos', 'joint_pos_rel', 18), ('joint_vel', 'joint_vel_rel', 18),
           ('left_gripper_pos', 'gripper_joint_position', 1), ('actions', 'last_action', 7),
           ('left_tcp_pos', 'tcp_position_in_robot_root_frame', 3),
           ('left_tcp_quat', 'tcp_orientation_in_robot_root_frame', 4)]
    configs = []
    for name, function_name, _ in obs:
        def function():
            pass
        function.__name__ = function_name
        params = {}
        if name == 'left_gripper_pos':
            params['robot_cfg'] = NS(name='robot', joint_names=['openarm_left_finger_joint1'], preserve_order=True)
        configs.append(NS(func=function, params=params, scale=None))
    return NS(scene={'robot': robot}, action_manager=NS(active_terms=list(terms), get_term=terms.__getitem__),
              observation_manager=NS(active_terms={'policy': [o[0] for o in obs]},
                                     _group_obs_term_cfgs={'policy': configs},
                                     group_obs_term_dim={'policy': [(o[2],) for o in obs]}),
              recorder_manager=NS(get_ep_meta=lambda: {'sim_args': {'dt': 1 / 120, 'decimation': 4}}),
              cfg=NS(sim=NS(dt=1 / 120), decimation=4))


class MetadataTests(unittest.TestCase):
    def test_native_order_processed_order_units_and_quaternion_components(self):
        env = environment()
        schema = collect(env)
        self.assertEqual(schema['fields']['obs/joint_pos']['names'], env.scene['robot'].joint_names)
        self.assertEqual(schema['fields']['processed_actions']['names'][-2:],
                         ['openarm_left_finger_joint2', 'openarm_left_finger_joint1'])
        self.assertEqual(schema['fields']['obs/left_gripper_pos']['names'], ['openarm_left_finger_joint1'])
        self.assertEqual(schema['fields']['obs/left_tcp_quat']['names'], ['qx', 'qy', 'qz', 'qw'])
        self.assertEqual(schema['fields']['actions']['physical_scale'], [.02, .02, .02, .1, .1, .1, 1])
        self.assertEqual(schema['fields']['obs/joint_pos']['phase'], 'pre_step')
        self.assertEqual(schema['fields']['states/articulation/robot/joint_position']['phase'], 'post_step')

    def test_resolved_observation_subset_retains_requested_order(self):
        env = environment()
        cfg = env.observation_manager._group_obs_term_cfgs['policy'][0]
        cfg.params['asset_cfg'] = NS(name='robot', joint_names=['openarm_left_joint3', 'openarm_right_joint1'], preserve_order=True)
        env.observation_manager.group_obs_term_dim['policy'][0] = (2,)
        self.assertEqual(collect(env)['fields']['obs/joint_pos']['names'], cfg.params['asset_cfg'].joint_names)

    def test_attach_is_idempotent_and_returned_metadata_cannot_mutate_later_exports(self):
        env = environment()
        expected = copy.deepcopy(attach(env))
        attach(env)
        first = env.recorder_manager.get_ep_meta()
        first['semantic_metadata']['fields']['actions']['names'][0] = 'corrupted'
        self.assertEqual(env.recorder_manager.get_ep_meta()['semantic_metadata'], expected)

    def test_rejects_different_control_semantics_and_unknown_observation(self):
        env = environment()
        env.action_manager.get_term('left_arm_action').cfg.controller.use_relative_mode = False
        with self.assertRaisesRegex(ValueError, 'Unsupported action semantics'):
            collect(env)
        env = environment()
        env.observation_manager._group_obs_term_cfgs['policy'][0].func.__name__ = 'normalized_joint_position'
        with self.assertRaisesRegex(ValueError, 'relative position'):
            collect(env)

    def test_real_sync_attribute_writer_and_spawn_export_preserve_metadata(self):
        env = environment()
        schema = attach(env)
        root = Path(os.environ.get('WORLDSIM_SOURCE_ROOT', Path(__file__).resolve().parents[2]))
        path = root / 'AutoData/submodules/IsaacLab-Arena/submodules/IsaacLab/source/isaaclab/isaaclab/utils/datasets/hdf5_dataset_file_handler.py'
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'HDF5DatasetFileHandler')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'add_env_args')
        namespace = {'json': json}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with h5py.File(root / 'sync.hdf5', 'w') as f:
                handler = NS(_env_args={}, _hdf5_data_group=f.create_group('data'), _raise_if_not_initialized=lambda: None)
                namespace['add_env_args'](handler, env.recorder_manager.get_ep_meta())
                self.assertEqual(json.loads(f['data'].attrs['env_args'])['semantic_metadata'], schema)
            pool = ExportPool(root / 'async.hdf5', workers=1, memory_bytes=2 * 1024**2, timeout=30)
            try:
                pool.submit({'actions': np.zeros((2, 7), dtype=np.float32)}, env_args=env.recorder_manager.get_ep_meta(),
                            attributes={'success': True})
                pool.finish()
            finally:
                if not pool.closed:
                    pool.abort('test cleanup')
            with h5py.File(root / 'async.hdf5', 'r') as f:
                self.assertEqual(json.loads(f['data'].attrs['env_args'])['semantic_metadata'], schema)


if __name__ == '__main__':
    unittest.main()
