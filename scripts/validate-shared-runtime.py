#!/usr/bin/env python3
"""Run shared task checks in one existing GPU runtime; invoke once per backend."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'workspace-overlays/shared_config'), str(ROOT / 'AutoData')]


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['autodata', 'arena'], required=True)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/openarm/experiment.json')
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--device', default='cuda:0')
    args = parser.parse_args()
    args.run_dir = args.run_dir.resolve()
    args.run_dir.mkdir(parents=True, exist_ok=False)
    result = {'backend': args.backend, 'status': 'started', 'interpreter': sys.executable,
              'scope': 'environment construction, action processing, short steps and direct success predicate cases'}
    app = env = None
    try:
        spec = importlib.util.spec_from_file_location('shared_launcher', ROOT / 'scripts/shared-config.py')
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        mode = 'generate' if args.backend == 'autodata' else 'evaluate'
        snapshot = launcher.plan(args.config, mode, args.run_dir, sys.executable,
                                 str(args.run_dir / 'unused-input.hdf5'), str(args.run_dir / 'unused-output.hdf5'), args.device)
        write(args.run_dir / 'resolved_config.json', snapshot)
        for key, value in snapshot['native'].items():
            write(args.run_dir / (key + '.json'), value)
        os.environ['WORLDSIM_RESOLVED_CONFIG'] = str(args.run_dir / 'resolved_config.json')
        os.environ['WORLDSIM_AUTODATA_ROOT'] = str(ROOT / 'AutoData')
        result['task_contract_hash'] = snapshot['task_contract_hash']
        from isaaclab.app import AppLauncher
        app = AppLauncher(headless=True, enable_cameras=True, device=args.device,
                          kit_args='--enable omni.usd.schema.omni_lens_distortion').app
        import gymnasium as gym
        import torch
        import isaaclab.utils.math as math_utils
        from openarm_autodata.tasks.pick_place.configs import scene_cfg
        from shared_config.runtime import make_env_cfg
        import openarm_autodata
        import isaaclab
        result['package_paths'] = {'openarm_autodata': openarm_autodata.__file__, 'isaaclab': isaaclab.__file__}
        c = snapshot['experiment']['common']
        if args.backend == 'autodata':
            import shared_config.generation  # noqa: F401
            from autodata_interfaces.env.isaaclab_env_interface import setup_env_config
            from autodata_interfaces.env.env_profile import EnvironmentProfile
            from autodata_interfaces.tasks.task_descriptor import TaskDescriptor
            from autodata_interfaces.embodiments.factory import embodiment_adapter_from_yaml
            task = TaskDescriptor.from_yaml(args.run_dir / 'task_descriptor.json')
            embodiment_adapter_from_yaml(args.run_dir / 'embodiment.json')
            cfg, success = setup_env_config(
                env_name=c['gym_id'], output_dir=str(args.run_dir / 'recorder'), output_file_name='probe',
                num_envs=1, device=args.device, generation_policy_params=task.get_generation_policy(),
                env_profile=EnvironmentProfile.from_yaml(str(args.run_dir / 'env_profile.json')))
            result['generation_terminations_removed'] = cfg.terminations is None
            env = gym.make(c['gym_id'], cfg=cfg).unwrapped
        else:
            from shared_config.arena import CompatibleOpenArmEnvironment
            from isaaclab_arena.environments.arena_env_builder import ArenaEnvBuilder, ArenaEnvBuilderCfg
            import isaaclab_arena
            result['package_paths']['isaaclab_arena'] = isaaclab_arena.__file__
            description = CompatibleOpenArmEnvironment().get_env(argparse.Namespace(
                openarm_episode_length_s=snapshot['experiment']['evaluation']['episode_length_s'],
                openarm_replay_fixture=None))
            termination = description.task.get_termination_cfg()
            success = termination.success[0].predicate_sequence[0]
            result['arena_success_objectives'] = [objective.name for objective in termination.success]
            env = ArenaEnvBuilder(description, ArenaEnvBuilderCfg(
                num_envs=1, env_spacing=2.0, seed=snapshot['effective_seed'],
                solve_relations=False, device=args.device)).make_registered().unwrapped
        obs, _ = env.reset()
        result['environment_loaded'] = True
        result['action_shape'] = list(env.action_space.shape)
        assert result['action_shape'] == [1, 7], result['action_shape']
        result['physics_dt'] = env.physics_dt
        result['step_dt'] = env.step_dt
        result['reset_pose_range'] = env.cfg.events.reset_cube.params['pose_range']
        result['success_function'] = success.func.__module__ + ':' + success.func.__name__
        result['success_params'] = {key: value for key, value in success.params.items()
                                    if type(value) in (int, float, str, bool)}
        result['observations'] = {key: {'shape': list(value.shape), 'dtype': str(value.dtype)}
                                  for key, value in obs['policy'].items()}
        arm = env.action_manager.get_term('left_arm_action')
        gripper = env.action_manager.get_term('left_gripper_action')
        action = torch.full((1, 7), 0.1, device=env.device)
        action[:, -1] = -1
        env.action_manager.process_action(action)
        expected = action[:, :6] * torch.tensor(env.cfg.actions.left_arm_action.scale, device=env.device)
        assert torch.allclose(arm.processed_actions, expected, atol=1e-7)
        result['processed_arm_probe'] = arm.processed_actions.cpu().tolist()
        close = gripper.processed_actions.clone()
        action[:, -1] = 1
        env.action_manager.process_action(action)
        opened = gripper.processed_actions.clone()
        assert torch.all(opened > close), (opened, close)
        result['gripper_targets'] = {'negative': close.cpu().tolist(), 'positive': opened.cpu().tolist()}
        # Exercise actual physics without assuming numerically identical cross-version trajectories.
        for index in range(6):
            action.zero_()
            action[:, 0] = 0.05 if index < 3 else -0.05
            action[:, -1] = -1 if index < 3 else 1
            obs, _, _, _, _ = env.step(action)
        result['physics_steps_completed'] = 6
        robot, table, cube = (env.scene[name] for name in ('robot', 'table', 'cube'))
        finger_ids, _ = robot.find_joints(['openarm_left_finger_joint1', 'openarm_left_finger_joint2'])
        joint_positions = robot.data.joint_pos.torch.clone()
        root_quat = table.data.root_quat_w.torch.clone()
        local = torch.tensor([[sum(scene_cfg.SCANNED_PAD_BOUNDS_TABLE[0]) / 2,
                               sum(scene_cfg.SCANNED_PAD_BOUNDS_TABLE[1]) / 2,
                               scene_cfg.SCANNED_PAD_SURFACE_Z_TABLE + scene_cfg.CUBE_HALF_SIZE]], device=env.device)

        def place(position, released=True, linear=0.0, angular=0.0):
            world = table.data.root_pos_w.torch + math_utils.quat_apply(root_quat, position)
            cube.write_root_pose_to_sim(torch.cat((world, root_quat), dim=-1))
            velocity = torch.zeros((1, 6), device=env.device)
            velocity[:, 0], velocity[:, 5] = linear, angular
            cube.write_root_velocity_to_sim(velocity)
            joints = joint_positions.clone()
            joints[:, finger_ids] = 0.7 if released else 0.0
            robot.write_joint_state_to_sim(joints, torch.zeros_like(joints))
            env.scene.update(env.physics_dt)
            return success.func(env, **success.params).cpu().tolist()

        cases = {'inside_released_still': place(local)}
        outside = local.clone()
        outside[:, 0] = scene_cfg.SCANNED_PAD_BOUNDS_TABLE[0][0] - 0.05
        cases['outside_pad'] = place(outside)
        above = local.clone()
        above[:, 2] += max(0.08, c['success']['height_tolerance'] * 3)
        cases['above_pad'] = place(above)
        cases['gripper_closed'] = place(local, released=False)
        cases['moving_linear'] = place(local, linear=c['success']['max_linear_speed'] * 3 + 0.1)
        cases['moving_angular'] = place(local, angular=c['success']['max_angular_speed'] * 3 + 0.1)
        result['success_cases'] = cases
        assert cases['inside_released_still'] == [True], cases
        assert all(value == [False] for key, value in cases.items() if key != 'inside_released_still'), cases
        result['status'] = 'passed'
    except BaseException:
        result['status'] = 'failed'
        result['traceback'] = traceback.format_exc()
        raise
    finally:
        write(args.run_dir / 'runtime_result.json', result)
        print(json.dumps(result, indent=2), flush=True)
        if env is not None:
            env.close()
        if app is not None:
            app.close()


if __name__ == '__main__':
    main()
