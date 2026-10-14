"""Shared environment factory, imported only after simulator startup."""
import hashlib
import os
from pathlib import Path

from shared_config.config import read


def apply_common(cfg, common, seed):
    """Apply the same physical task contract in generation and evaluation."""
    cfg.seed = seed
    action = common['action']
    cfg.actions.left_arm_action.scale = (action['position_scale_m'],) * 3 + (action['rotation_scale_rad'],) * 3
    cfg.events.reset_cube.params['pose_range'] = {key: tuple(value) for key, value in common['reset_pose_range'].items()}
    cfg.terminations.success.params.update(common['success'])
    return cfg


def make_env_cfg():
    """Construct the unique AutoData source environment using a resolved snapshot."""
    snapshot = read(os.environ['WORLDSIM_RESOLVED_CONFIG'])
    root = Path(os.environ['WORLDSIM_AUTODATA_ROOT']).parent
    for relative, expected_hash in snapshot['source_hashes'].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected_hash:
            raise RuntimeError(f'Source changed after resolution: {relative}')
    from openarm_autodata.tasks.pick_place.configs import left_env_cfg
    expected = Path(os.environ['WORLDSIM_AUTODATA_ROOT']) / 'openarm_autodata/tasks/pick_place/configs/left_env_cfg.py'
    if Path(left_env_cfg.__file__).resolve() != expected.resolve():
        raise RuntimeError('A duplicate openarm_autodata package shadows the shared source')
    c = snapshot['experiment']['common']
    return apply_common(left_env_cfg.OpenArmLeftPickPlaceEnvCfg(), c, snapshot['effective_seed'])
