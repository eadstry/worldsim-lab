# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Explicit GPU smoke: capture real joint order and save three steps with metadata.

Requires an already configured Isaac Sim environment; submit through the host queue.
This does not generate a successful task demonstration or train a policy.
"""
import argparse
import json
import sys
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    root = args.source_root.resolve()
    sys.path[:0] = [str(Path(__file__).resolve().parent), str(root / 'workspace-overlays/openarm-production/runtime'), str(root / 'AutoData')]
    from isaaclab.app import AppLauncher
    launcher = AppLauncher(headless=True, enable_cameras=True, kit_args='--enable omni.usd.schema.omni_lens_distortion')
    app, env = launcher.app, None
    try:
        import gymnasium as gym
        import h5py
        import torch
        import openarm_autodata.tasks.pick_place  # noqa: F401
        from isaaclab_tasks.utils.parse_cfg import parse_env_cfg
        from isaaclab.envs.mdp.recorders.recorders_cfg import ActionStateRecorderManagerCfg
        from isaaclab.managers.recorder_manager import DatasetExportMode
        from dataset_metadata import attach

        task = 'Isaac-PickPlace-Cube-OpenArm-Bimanual-Left-IK-Rel-v0'
        cfg = parse_env_cfg(task, device='cuda:0', num_envs=1)
        cfg.env_name = task
        cfg.terminations = None
        cfg.observations.policy.concatenate_terms = False
        cfg.recorders = ActionStateRecorderManagerCfg()
        cfg.recorders.dataset_export_dir_path = str(args.output.resolve())
        cfg.recorders.dataset_filename = 'smoke'
        cfg.recorders.dataset_export_mode = DatasetExportMode.EXPORT_ALL
        cfg.recorders.export_in_record_pre_reset = False
        env = gym.make(task, cfg=cfg).unwrapped
        schema = attach(env)
        env.reset()
        for _ in range(3):
            env.step(torch.zeros((1, env.action_manager.total_action_dim), device=env.device))
        env.recorder_manager.export_episodes([0])
        env.close()
        env = None
        with h5py.File(args.output / 'smoke.hdf5', 'r') as f:
            saved = json.loads(f['data'].attrs['env_args'])['semantic_metadata']
            assert saved == schema
            assert len(f['data/demo_0/actions']) == 3
            assert saved['fields']['obs/joint_pos']['names'] == schema['articulations']['robot']['joint_names']
        report = dict(status='passed', steps=3, scope='GPU startup, zero-action stepping and synchronous metadata export only',
                      semantic_metadata=schema)
        (args.output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print('OPENARM_SEMANTIC_METADATA_RUNTIME_PASSED', flush=True)
    except BaseException:
        (args.output / 'result.json').write_text(json.dumps(dict(status='failed', traceback=traceback.format_exc()), indent=2) + '\n')
        raise
    finally:
        if env is not None:
            env.close()
        app.close()


if __name__ == '__main__':
    main()
