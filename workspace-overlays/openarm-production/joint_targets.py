# SPDX-License-Identifier: Apache-2.0
"""Record active-arm absolute joint state and controller targets without changing control.

The held arm command is computed by IK once per control step. The arm and
finger rate limiters ramp toward these commands on physics substeps. Record
both the requested command and the final applied target, never measured future
angles as an action. Original TCP commands remain available for provenance.
"""
import copy
from types import MethodType


def tensor(value):
    return getattr(value, 'torch', value)


def attach(env):
    import torch

    recorder = env.recorder_manager
    if getattr(recorder, '_openarm_joint_targets', False):
        return
    schema = recorder.get_ep_meta()['semantic_metadata']
    terms = [env.action_manager.get_term(n) for n in env.action_manager.active_terms]
    pose, fingers = terms
    robot = env.scene['robot']
    if not all(hasattr(pose, n) for n in ('_joint_pos_command', '_joint_pos_target')) or not hasattr(fingers, '_applied_targets'):
        raise ValueError('Joint target capture requires the verified held-IK and rate-limited finger controllers')
    names = list(robot.joint_names)
    def ids(term):
        return list(range(len(names)))[term._joint_ids] if isinstance(term._joint_ids, slice) else list(map(int, term._joint_ids))
    pose_ids, finger_ids = ids(pose), ids(fingers)
    arm = 'left' if all(names[i].startswith('openarm_left_joint') for i in pose_ids) else 'right'
    ordered_names = [f'openarm_{arm}_joint{i}' for i in range(1, 8)] + [f'openarm_{arm}_finger_joint{i}' for i in (1, 2)]
    native_ids = [names.index(n) for n in ordered_names]
    target_names = [names[i] for i in pose_ids + finger_ids]
    if len(target_names) != 9 or set(target_names) != set(ordered_names):
        raise ValueError('Joint target capture requires exactly seven arm and two finger joints')
    order = [target_names.index(n) for n in ordered_names]
    if tensor(pose._joint_pos_command).shape[-1] != 7 or tensor(fingers.processed_actions).shape[-1] != 2:
        raise ValueError('Unexpected joint command buffer dimensions')
    specs = {
        'obs/joint_pos_absolute': dict(phase='pre_step', representation='absolute_joint_position'),
        'joint_actions': dict(phase='control_step_target', representation='absolute_joint_position_target'),
        'joint_applied_targets': dict(phase='post_step', representation='absolute_final_physics_substep_position_target'),
    }
    schema = copy.deepcopy(schema)
    for path, spec in specs.items():
        if path in schema['fields']:
            raise ValueError('Refuse to overwrite existing joint target metadata')
        schema['fields'][path] = dict(names=ordered_names, units=['rad'] * 9, **spec)
    schema['joint_control'] = dict(names=ordered_names, arm=arm, units=['rad'] * 9,
        action_source='held IK _joint_pos_command plus binary finger processed_actions',
        timing='Action command resolved during the recorded control step; state measured before the same step.',
        rate_limiting='Arm and finger commands are approached on physics substeps; joint_applied_targets is the final substep target.',
        max_arm_velocity_rad_s=float(pose.cfg.max_joint_velocity), max_finger_velocity_rad_s=float(fingers.cfg.max_velocity))
    original_meta = recorder.get_ep_meta
    original_pre, original_post = recorder.record_pre_step, recorder.record_post_step

    def get_ep_meta(instance):
        metadata = dict(original_meta())
        metadata['semantic_metadata'] = copy.deepcopy(schema)
        return metadata

    def record_pre_step(instance):
        original_pre()
        instance.add_to_episodes('obs/joint_pos_absolute', tensor(robot.data.joint_pos)[:, native_ids])

    def record_post_step(instance):
        original_post()
        command = torch.cat((tensor(pose._joint_pos_command), tensor(fingers.processed_actions)), dim=-1)[:, order]
        applied = torch.cat((tensor(pose._joint_pos_target), tensor(fingers._applied_targets)), dim=-1)[:, order]
        instance.add_to_episodes('joint_actions', command)
        instance.add_to_episodes('joint_applied_targets', applied)

    recorder.get_ep_meta = MethodType(get_ep_meta, recorder)
    recorder.record_pre_step = MethodType(record_pre_step, recorder)
    recorder.record_post_step = MethodType(record_post_step, recorder)
    recorder._openarm_joint_targets = True
