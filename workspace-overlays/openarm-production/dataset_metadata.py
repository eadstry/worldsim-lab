# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Persist OpenArm field semantics through both synchronous and async recorders.

No simulation dependency is imported here. Joint order comes from the live
articulation, never from URDF declaration or actuator configuration order.
"""
from __future__ import annotations

import copy
import json
from types import MethodType

import numpy as np

POSE_NAMES = ['x', 'y', 'z', 'qx', 'qy', 'qz', 'qw']
ACTION_NAMES = ['delta_x', 'delta_y', 'delta_z', 'delta_rx', 'delta_ry', 'delta_rz', 'gripper']


def as_numpy(value):
    value = getattr(value, 'torch', value)
    if hasattr(value, 'detach'):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def openarm_schema(joint_names, arm, action_scale, default_positions, evidence):
    """Build the explicit OpenArm v2 revolute-joint / XYZW profile."""
    names = list(joint_names)
    expected = {f'openarm_{side}_joint{i}' for side in ('left', 'right') for i in range(1, 8)}
    expected |= {f'openarm_{side}_finger_joint{i}' for side in ('left', 'right') for i in (1, 2)}
    if len(names) != 18 or set(names) != expected:
        raise ValueError('OpenArm metadata requires the 18 actual v2 joint names, in runtime order')
    if arm not in ('left', 'right') or len(action_scale) != 6 or len(default_positions) != 18:
        raise ValueError('Invalid OpenArm control profile')
    if not np.isfinite([*action_scale, *default_positions]).all():
        raise ValueError('Non-finite metadata')
    fields = {}

    def add(path, labels, units, phase, frame=None, **extra):
        fields[path] = dict(names=list(labels), units=list(units), phase=phase, **extra)
        if frame:
            fields[path]['frame'] = frame

    add('actions', ACTION_NAMES, ['1'] * 7, 'pre_step', 'robot_root',
        representation='scaled_delta_position_axis_angle_and_binary_gripper',
        physical_scale=list(action_scale) + [1.0], physical_units=['m'] * 3 + ['rad'] * 3 + ['1'])
    add('obs/actions', ACTION_NAMES, ['1'] * 7, 'pre_step', representation='previous_action')
    add('obs/joint_pos', names, ['rad'] * 18, 'pre_step', representation='relative_to_default_joint_position')
    add('obs/joint_vel', names, ['rad/s'] * 18, 'pre_step', representation='relative_to_default_joint_velocity')
    add(f'obs/{arm}_gripper_pos', [f'openarm_{arm}_finger_joint1'], ['rad'], 'pre_step')
    for suffix, frame in [('', 'robot_root'), ('_env', 'environment_origin')]:
        add(f'obs/{arm}_tcp_pos{suffix}', ['x', 'y', 'z'], ['m'] * 3, 'pre_step', frame)
        add(f'obs/{arm}_tcp_quat{suffix}', ['qx', 'qy', 'qz', 'qw'], ['1'] * 4, 'pre_step', frame)
    for obj in ('cube', 'table'):
        add(f'obs/{obj}_pose', POSE_NAMES, ['m'] * 3 + ['1'] * 4, 'pre_step', 'robot_root')
    processed = ACTION_NAMES[:6] + [f'openarm_{arm}_finger_joint{i}' for i in (1, 2)]
    add('processed_actions', processed, ['m'] * 3 + ['rad'] * 5, 'post_step', 'robot_root',
        representation='scaled_pose_delta_and_finger_position_targets')
    for prefix, phase in [('states', 'post_step'), ('initial_state', 'post_reset')]:
        for obj in ('articulation/robot', 'rigid_object/cube', 'rigid_object/table'):
            add(f'{prefix}/{obj}/root_pose', POSE_NAMES, ['m'] * 3 + ['1'] * 4, phase, 'environment_origin')
            add(f'{prefix}/{obj}/root_velocity', ['vx', 'vy', 'vz', 'wx', 'wy', 'wz'],
                ['m/s'] * 3 + ['rad/s'] * 3, phase, 'world_axes')
        add(f'{prefix}/articulation/robot/joint_position', names, ['rad'] * 18, phase, representation='absolute_joint_position')
        add(f'{prefix}/articulation/robot/joint_velocity', names, ['rad/s'] * 18, phase, representation='absolute_joint_velocity')
    return dict(schema_version=1, profile='openarm_v2_ik_relative_xyzw', quaternion_order='xyzw',
                articulations={'robot': dict(joint_names=names, joint_units=['rad'] * 18,
                                             default_joint_positions=list(default_positions))},
                fields=fields, evidence=copy.deepcopy(evidence))


def collect(env):
    """Capture the resolved OpenArm runtime layout once, before any episode is exported."""
    robot = env.scene['robot']
    names = list(robot.joint_names)
    defaults = as_numpy(robot.data.default_joint_pos)
    if not np.all(defaults == defaults[0]):
        raise ValueError('Per-environment default joint offsets differ; a single dataset schema is unsafe')
    terms = [(name, env.action_manager.get_term(name)) for name in env.action_manager.active_terms]
    if len(terms) != 2:
        raise ValueError('Expected an OpenArm relative-pose term followed by a binary gripper term')
    pose, gripper = terms[0][1], terms[1][1]
    controller = pose.cfg.controller
    if pose.action_dim != 6 or not controller.use_relative_mode or controller.command_type != 'pose':
        raise ValueError('Unsupported action semantics; refuse to label unknown controls')
    if gripper.action_dim != 1 or as_numpy(pose.processed_actions).shape[-1] != 6 or as_numpy(gripper.processed_actions).shape[-1] != 2:
        raise ValueError('Unexpected processed action layout')
    if not hasattr(gripper.cfg, 'open_command_expr') or not hasattr(gripper.cfg, 'close_command_expr'):
        raise ValueError('Expected binary gripper position control')
    pose_ids = list(range(len(names)))[pose._joint_ids] if isinstance(pose._joint_ids, slice) else list(pose._joint_ids)
    controlled = [names[int(i)] for i in pose_ids]
    arm = 'left' if all(n.startswith('openarm_left_joint') for n in controlled) else 'right'
    if set(controlled) != {f'openarm_{arm}_joint{i}' for i in range(1, 8)}:
        raise ValueError('Unexpected controlled joint set')
    gripper_ids = (list(range(len(names)))[gripper._joint_ids] if isinstance(gripper._joint_ids, slice)
                   else list(map(int, gripper._joint_ids)))
    gripper_names = [names[i] for i in gripper_ids]
    if set(gripper_names) != {f'openarm_{arm}_finger_joint{i}' for i in (1, 2)}:
        raise ValueError('Pose and gripper action terms control different arms')
    scale = np.broadcast_to(np.asarray(pose.cfg.scale, dtype=float), (6,)).tolist()
    schema = openarm_schema(names, arm, scale, defaults[0].tolist(), dict(kind='runtime', source='env.scene.robot.joint_names'))
    schema['fields']['processed_actions']['names'] = ACTION_NAMES[:6] + gripper_names
    schema['action_terms'] = [dict(name=name, class_name=type(term).__name__, action_dim=int(term.action_dim),
                                   processed_dim=int(as_numpy(term.processed_actions).shape[-1])) for name, term in terms]
    schema['gripper_commands'] = dict(open=gripper.cfg.open_command_expr, close=gripper.cfg.close_command_expr)
    # Validate that labels describe the actual observation functions and selections.
    manager = env.observation_manager
    term_names = manager.active_terms['policy']
    configs = manager._group_obs_term_cfgs['policy']
    dimensions = manager.group_obs_term_dim['policy']
    functions = {}
    for name, cfg, shape in zip(term_names, configs, dimensions, strict=True):
        path = 'obs/' + name
        func = getattr(cfg.func, '__name__', type(cfg.func).__name__)
        functions[path] = dict(function=func, shape=list(shape))
        if path not in schema['fields']:
            if name.endswith('_rgb') and len(shape) == 3 and shape[-1] == 3:
                schema['fields'][path] = dict(names=['height', 'width', 'channels'], phase='pre_step',
                                              representation='rgb', units=['pixel', 'pixel', 'channel'])
                continue
            raise ValueError(f'Missing explicit semantics for {path}')
        spec = schema['fields'][path]
        if len(shape) != 1:
            raise ValueError(f'Unsupported observation shape: {path} {shape}')
        if name in ('joint_pos', 'joint_vel') or name.endswith('_gripper_pos'):
            asset_cfg = cfg.params.get('asset_cfg', cfg.params.get('robot_cfg'))
            if asset_cfg is not None:
                asset = env.scene[asset_cfg.name]
                if asset is not robot:
                    raise ValueError(f'{path}: expected robot articulation')
                if asset_cfg.joint_names is not None:
                    ids, _ = robot.find_joints(asset_cfg.joint_names, preserve_order=asset_cfg.preserve_order)
                else:
                    ids = asset_cfg.joint_ids
                selected = list(range(len(names)))[ids] if isinstance(ids, slice) else list(map(int, ids))
                spec['names'] = [names[i] for i in selected]
            if name == 'joint_pos' and func != 'joint_pos_rel':
                raise ValueError('joint_pos is not the expected relative position observation')
            if name == 'joint_vel' and func != 'joint_vel_rel':
                raise ValueError('joint_vel is not the expected relative velocity observation')
        expected_functions = {
            'actions': 'last_action', 'cube_pose': 'object_pose_in_robot_root_frame',
            'table_pose': 'object_pose_in_robot_root_frame',
            f'{arm}_tcp_pos': 'tcp_position_in_robot_root_frame',
            f'{arm}_tcp_quat': 'tcp_orientation_in_robot_root_frame',
            f'{arm}_tcp_pos_env': 'tcp_position_in_env_frame',
            f'{arm}_tcp_quat_env': 'tcp_orientation_in_env_frame',
            f'{arm}_gripper_pos': 'gripper_joint_position',
        }
        if name in expected_functions and func != expected_functions[name]:
            raise ValueError(f'{path}: observation function differs from the semantic profile')
        if len(spec['names']) != shape[0]:
            raise ValueError(f'{path}: names and observation dimensions differ')
        spec['units'] = spec['units'][:shape[0]]
        spec['observation_scale'] = cfg.scale
    schema['observation_terms'] = functions
    schema['articulations']['robot']['default_joint_velocities'] = as_numpy(robot.data.default_joint_vel)[0].tolist()
    schema['control_dt'] = float(env.cfg.sim.dt * env.cfg.decimation)
    # Fail immediately on non-serializable metadata, rather than in an export worker.
    return json.loads(json.dumps(schema, allow_nan=False))


def attach(env):
    """Add one immutable schema to get_ep_meta, used by sync and async export alike."""
    recorder = env.recorder_manager
    if getattr(recorder, '_openarm_semantic_metadata', None) is not None:
        return recorder._openarm_semantic_metadata
    schema = collect(env)
    original = recorder.get_ep_meta
    if 'semantic_metadata' in original():
        raise ValueError('Refuse to overwrite existing semantic_metadata')

    def get_ep_meta(instance):
        metadata = dict(original())
        if 'semantic_metadata' in metadata:
            raise ValueError('Refuse to overwrite existing semantic_metadata')
        metadata['semantic_metadata'] = copy.deepcopy(schema)
        return metadata

    recorder.get_ep_meta = MethodType(get_ep_meta, recorder)
    recorder._openarm_semantic_metadata = copy.deepcopy(schema)
    return copy.deepcopy(schema)
