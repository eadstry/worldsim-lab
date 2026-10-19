# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Probe the prepared OpenArm task with real resets and RGB rendering."""
import argparse
import hashlib
import json
import sys
import traceback
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
root = Path(__file__).resolve().parents[2]
production = root / 'workspace-overlays/openarm-production'
sys.path[:0] = [str(production / 'runtime'), str(root / 'AutoData')]
from isaaclab.app import AppLauncher

launcher = AppLauncher(headless=True, enable_cameras=True,
                       kit_args='--enable omni.usd.schema.omni_lens_distortion')
app = launcher.app
env = None
try:
    import gymnasium as gym
    import numpy as np
    import torch
    from PIL import Image
    import openarm_autodata.tasks.pick_place
    from isaaclab_tasks.utils.parse_cfg import parse_env_cfg

    task = 'Isaac-PickPlace-Cube-OpenArm-Bimanual-Left-IK-Rel-v0'
    cfg = parse_env_cfg(task, device='cuda:0', num_envs=4)
    cfg.num_rerenders_on_reset = 3
    env = gym.make(task, cfg=cfg).unwrapped
    cube = env.scene['cube']
    ranges = dict(cfg.events.reset_cube.params['pose_range'])
    center = cube.data.default_root_state[0, :3].cpu().numpy()

    def pose():
        return (cube.data.root_pos_w - env.scene.env_origins).cpu().numpy().copy()

    samples, rotations, frame_records = [], [], []
    for batch in range(64):
        env.reset(seed=101 if batch == 0 else None)
        samples.extend(pose().tolist())
        rotations.extend(cube.data.root_quat_w.cpu().numpy().tolist())
        if batch < 9:
            # A physics/control step propagates the reset transforms to RTX/Fabric.
            env.step(torch.zeros(env.action_space.shape, device=env.device))
            for _ in range(3):
                env.sim.render()
            camera = env.scene['third_person_camera']
            camera.update(env.step_dt, force_recompute=True)
            rgb = camera.data.output['rgb'][0, ..., :3].cpu().numpy()
            filename = f'reset-{batch:02d}.png'
            Image.fromarray(rgb).save(args.output / filename)
            # Fixed diagnostic view makes workspace coverage visible despite wrist occlusion.
            camera.set_world_poses_from_view(
                env.scene.env_origins + torch.tensor([.85, .65, 1.8], device=env.device),
                env.scene.env_origins + torch.tensor([.53, .12, 1.06], device=env.device))
            for _ in range(3):
                env.sim.render()
            camera.update(env.step_dt, force_recompute=True)
            overview = f'overview-{batch:02d}.png'
            Image.fromarray(camera.data.output['rgb'][0, ..., :3].cpu().numpy()).save(args.output / overview)
            frame_records.append({'file': filename, 'position': pose()[0].tolist(),
                                  'overview': overview, 'reset_position': samples[-4],
                                  'control_steps_after_reset': 1})
        if batch % 8 == 0:
            print(f'RESET_BATCH {batch}/64', flush=True)
    samples = np.array(samples)
    rotations = np.array(rotations)

    def sequence(seed):
        values = []
        for i in range(8):
            env.reset(seed=seed if i == 0 else None)
            values.append(np.concatenate([pose(), cube.data.root_quat_w.cpu().numpy()], axis=1))
        return np.array(values)

    first, repeated, other = sequence(2026), sequence(2026), sequence(2027)
    term = env.event_manager.get_term_cfg('reset_cube')
    term.params['pose_range'] = {k: (0.0, 0.0) for k in ranges}
    env.event_manager.set_term_cfg('reset_cube', term)
    fixed = sequence(101)
    delta = samples - center
    checks = {
        'finite_poses': bool(np.isfinite(samples).all()),
        'configured_bounds': all(bool(((delta[:, i] >= ranges[k][0] - 1e-5) &
                                      (delta[:, i] <= ranges[k][1] + 1e-5)).all())
                                 for i, k in enumerate(('x', 'y'))),
        'xy_changes': bool((np.ptp(delta[:, :2], axis=0) > .02).all()),
        'z_fixed': bool(np.max(np.abs(delta[:, 2])) < 1e-5),
        'orientation_fixed': bool(np.max(np.abs(rotations - rotations[0])) < 1e-5),
        'same_seed_reproduces': bool(np.allclose(first, repeated, atol=1e-6, rtol=0)),
        'different_seed_changes': bool(not np.allclose(first, other, atol=1e-6, rtol=0)),
        'disabled_randomization_fixed': bool(np.max(np.abs(fixed[..., :3] - center)) < 1e-5),
    }
    # Execute short physics/control smoke test after the reset-only measurements.
    term.params['pose_range'] = ranges
    env.event_manager.set_term_cfg('reset_cube', term)
    env.reset(seed=101)
    for _ in range(12):
        env.step(torch.zeros(env.action_space.shape, device=env.device))
    checks['physics_steps_finite'] = bool(torch.isfinite(cube.data.root_state_w).all())
    sources = [Path(__file__), production / 'runtime/openarm_autodata/tasks/pick_place/configs/scene_cfg.py',
               production / 'runtime/openarm_autodata/tasks/pick_place/configs/env_cfg.py',
               production / 'runtime/openarm_autodata/tasks/pick_place/configs/left_env_cfg.py']
    result = {'status': 'passed' if all(checks.values()) else 'failed', 'task': task,
              'sample_count': len(samples), 'num_envs': 4, 'seed': 101,
              'pose_range': ranges, 'center_m': center.tolist(), 'checks': checks,
              'same_seed_max_error': float(np.max(np.abs(first - repeated))),
              'mean_offset_m': delta.mean(axis=0).tolist(),
              'std_offset_m': delta.std(axis=0).tolist(),
              'frames': frame_records, 'physics_steps': 12,
              'source_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              'scope': 'Reset-event and rendering validation; no trajectory generation or success-rate evaluation.'}
    np.savez(args.output / 'samples.npz', positions=samples, quaternions=rotations,
             repeat_a=first, repeat_b=repeated, other_seed=other, disabled=fixed)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
    if not all(checks.values()):
        raise RuntimeError('One or more checks failed; inspect result.json')
except BaseException:
    (args.output / 'error.txt').write_text(traceback.format_exc())
    raise
finally:
    if env is not None:
        env.close()
    app.close()
