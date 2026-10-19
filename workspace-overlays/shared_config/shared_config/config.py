"""Resolve portable configuration without importing simulation dependencies."""
import copy
import hashlib
import json
import math
from pathlib import Path

GYM_ID = 'Isaac-PickPlace-Cube-OpenArm-Bimanual-Left-IK-Rel-v0'


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected.split()):
        raise ValueError(f'{label}: expected exactly {expected}')


def positive(value, label, integer=False):
    valid = type(value) is int if integer else type(value) in (int, float)
    if not valid or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{label}: expected positive {"integer" if integer else "number"}')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def resolve(path):
    path = Path(path).resolve()
    cfg = read(path)
    keys(cfg, 'schema_version task_id common generation evaluation', 'experiment')
    if type(cfg['schema_version']) is not int or cfg['schema_version'] != 1:
        raise ValueError('Unsupported schema_version')
    if not isinstance(cfg['task_id'], str) or not cfg['task_id']:
        raise ValueError('task_id must be nonempty')
    c, g, e = cfg['common'], cfg['generation'], cfg['evaluation']
    keys(c, 'gym_id seed action reset_pose_range success', 'common')
    if c['gym_id'] != GYM_ID:
        raise ValueError('Only OpenArm left relative IK is supported')
    for seed in (c['seed'], e.get('seed')):
        if type(seed) is not int or seed < 0:
            raise ValueError('Seeds must be nonnegative integers')
    keys(c['action'], 'position_scale_m rotation_scale_rad gripper_negative', 'action')
    if c['action']['gripper_negative'] != 'close':
        raise ValueError('Only negative-close gripper convention is supported')
    for key in ('position_scale_m', 'rotation_scale_rad'):
        positive(c['action'][key], key)
    keys(c['reset_pose_range'], 'x y', 'reset_pose_range')
    for limits in c['reset_pose_range'].values():
        if (not isinstance(limits, list) or len(limits) != 2
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in limits)
                or limits[0] > limits[1]):
            raise ValueError('Reset limits must be finite [min, max]')
    keys(c['success'], 'height_tolerance release_position max_linear_speed max_angular_speed', 'success')
    for key, value in c['success'].items():
        positive(value, key)
    keys(g, 'task_descriptor embodiment env_profile num_envs', 'generation')
    keys(e, 'seed num_envs num_episodes episode_length_s policy_type policy_args', 'evaluation')
    for label, value in [('generation.num_envs', g['num_envs']), ('evaluation.num_envs', e['num_envs']),
                         ('num_episodes', e['num_episodes'])]:
        positive(value, label, integer=True)
    positive(e['episode_length_s'], 'episode_length_s')
    # Parallel completion batches can overshoot the requested episode budget.
    if e['num_episodes'] % e['num_envs']:
        raise ValueError('num_episodes must be divisible by evaluation.num_envs')
    if not isinstance(e['policy_type'], str) or not e['policy_type']:
        raise ValueError('policy_type must be a nonempty string')
    if not isinstance(e['policy_args'], dict):
        raise ValueError('policy_args must be a dictionary')
    reserved = {'seed','num_envs','num_episodes','num_steps','device','output_base_dir',
                'external_environment_class_path','policy_type','openarm_episode_length_s',
                'openarm_replay_fixture','enable_cameras','viz','kit_args'}
    for key, value in e['policy_args'].items():
        if not key.isidentifier() or key in reserved or type(value) not in (str, int, float):
            raise ValueError(f'Invalid or reserved policy argument: {key}')
    inputs = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}
    native = {}
    for key in ('task_descriptor', 'embodiment', 'env_profile'):
        ref = Path(g[key])
        if ref.is_absolute() or '..' in ref.parts:
            raise ValueError('Configuration references must stay relative to the manifest')
        ref = path.parent / ref
        native[key] = read(ref)
        inputs[g[key]] = hashlib.sha256(ref.read_bytes()).hexdigest()
    task, embodiment, profile = (native[k] for k in ('task_descriptor', 'embodiment', 'env_profile'))
    if task['algo'] != 'skillgen':
        raise ValueError('Only skillgen generation is supported')
    policy = task['generation_policy']
    if 'seed' in policy:
        raise ValueError('Define generation seed only in common.seed')
    positive(policy['num_trials'], 'num_trials', integer=True)
    policy['seed'] = c['seed']
    if embodiment['type'] != 'delta_pose_ik_single_arm' or embodiment['eef_name'] != 'left':
        raise ValueError('Embodiment must be left relative IK')
    layout = embodiment['action_layout']
    for key in ('position_action_scale', 'rotation_action_scale'):
        if key in layout:
            raise ValueError('Define action scales only in common.action')
    layout['position_action_scale'] = c['action']['position_scale_m']
    layout['rotation_action_scale'] = c['action']['rotation_scale_rad']
    # Scene/reset profile patches would bypass the shared factory; reject until supported.
    if set(profile) - {'name', 'description', 'base_env', 'planner'}:
        raise ValueError('Put shared reset parameters in common; profile patches are unsupported')
    if profile['base_env'] != c['gym_id'] or profile['planner'] != 'openarm_pick_place_left':
        raise ValueError('Environment profile conflicts with the shared task')
    return {'experiment': copy.deepcopy(cfg), 'native': native, 'input_hashes': inputs,
            'task_contract_hash': digest(c)}
