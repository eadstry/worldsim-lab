# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Queued task-completion experiments in a frozen OpenArm scene; never change production assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np

from metrics import PHASES, stable_success, summarize

VARIANTS = {
    'baseline': {}, 'kp_half': {'kp': .5}, 'kp_double': {'kp': 2.0},
    'kd_half': {'kd': .5}, 'kd_double': {'kd': 2.0},
    'gravity_ff': {'gravity_ff': True}, 'speed_half': {'speed': .5}, 'speed_double': {'speed': 2.0},
    'friction_half': {'friction': .5}, 'friction_double': {'friction': 2.0},
}


def unwrap(x):
    return getattr(x, 'torch', x)


def read_episode(path, name):
    with h5py.File(path, 'r') as f:
        d = f['data'][name]
        values = {key: d[key][:] for key in ['actions', 'obs/left_tcp_pos', 'obs/left_tcp_quat', 'obs/cube_pose']}
        state = {}
        def visit(key, value):
            if isinstance(value, h5py.Dataset):
                node = state
                parts = key.split('/')
                for part in parts[:-1]:
                    node = node.setdefault(part, {})
                node[parts[-1]] = value[:]
        d['initial_state'].visititems(visit)
        a = values['actions'][:, -1]
        transitions = np.flatnonzero(np.diff(a) != 0) + 1
        assert len(transitions) == 2 and a[0] > 0
        close, release = transitions.tolist()
        height = values['obs/cube_pose'][:, 2]
        lift = int(np.flatnonzero((np.arange(len(a)) > close) & (height >= height[0] + .04))[0])
        return dict(values=values, state=state, close=close, lift=lift, release=release)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--autodata-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--demos', nargs='+', default=['demo_0', 'demo_1', 'demo_2', 'demo_3'])
    p.add_argument('--variants', nargs='+', choices=list(VARIANTS), default=['baseline'])
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--physics-hz', type=int, choices=[60, 120, 240, 480], default=120)
    p.add_argument('--position-iterations', type=int, default=16)
    p.add_argument('--velocity-iterations', type=int, default=4)
    p.add_argument('--external-forces-every-iteration', action='store_true')
    p.add_argument('--timeout-s', type=float, default=120.)
    p.add_argument('--outer-gain', type=float, default=.25)
    p.add_argument('--gate-distance', type=float, default=.015)
    p.add_argument('--max-frames', type=int, default=None)
    args = p.parse_args()
    assert args.repeats > 0 and args.timeout_s > 0 and 0 < args.outer_gain <= 1
    assert args.physics_hz % 30 == 0
    args.output.mkdir(parents=True, exist_ok=False)
    episodes = {name: read_episode(args.source, name) for name in args.demos}
    assignments = [(v, d) for v in args.variants for d in args.demos]
    n = len(assignments)
    # Only import dependency libraries; this entrypoint belongs to the workspace overlay.
    sys.path[:0] = [str(args.runtime.resolve()), str(args.autodata_root.resolve())]
    from isaaclab.app import AppLauncher
    launcher = AppLauncher(headless=True, enable_cameras=False)
    app, env = launcher.app, None
    started = time.monotonic()
    try:
        import torch
        import gymnasium as gym
        from compat import install_task_compat
        install_task_compat()
        import openarm_autodata.tasks.pick_place  # noqa: F401
        from openarm_autodata.tasks.pick_place.envs import mdp
        from isaaclab.managers import ObservationTermCfg, SceneEntityCfg
        from isaaclab_tasks.utils.parse_cfg import parse_env_cfg
        from isaaclab.utils.math import compute_pose_error
        from isaaclab_physx.physics.physx_manager_cfg import PhysxCfg

        task = 'Isaac-PickPlace-Cube-OpenArm-Bimanual-Left-IK-Rel-v0'
        cfg = parse_env_cfg(task, device='cuda:0', num_envs=n)
        cfg.terminations = None
        cfg.recorders = None
        cfg.decimation = args.physics_hz // 30
        cfg.sim.dt = 1. / args.physics_hz
        cfg.sim.render_interval = cfg.decimation
        cfg.scene.env_spacing = 4.
        cfg.scene.robot.spawn.articulation_props.solver_position_iteration_count = args.position_iterations
        cfg.scene.robot.spawn.articulation_props.solver_velocity_iteration_count = args.velocity_iterations
        cfg.sim.physics = PhysxCfg(enable_external_forces_every_iteration=args.external_forces_every_iteration)
        for name in ['left_hand_camera', 'right_hand_camera', 'third_person_camera', 'ee_frame']:
            setattr(cfg.scene, name, None)
        for name, term in vars(cfg.observations.policy).items():
            if isinstance(term, ObservationTermCfg) and name not in ['joint_pos', 'joint_vel']:
                setattr(cfg.observations.policy, name, None)
        cfg.observations.subtask_terms = None
        env = gym.make(task, cfg=cfg).unwrapped
        assert abs(float(env.physics_dt)*cfg.decimation-1/30) < 1e-10
        robot, cube = env.scene['robot'], env.scene['cube']
        names = list(robot.joint_names)
        active = [f'openarm_left_joint{i}' for i in range(1, 8)] + ['openarm_left_finger_joint1', 'openarm_left_finger_joint2']
        ids = [names.index(name) for name in active]
        pose = env.action_manager.get_term('left_arm_action')
        fingers = env.action_manager.get_term('left_gripper_action')
        dev = env.device
        tensor = lambda x, **kw: torch.as_tensor(x, device=dev, **kw)
        # The same recorded initial states are paired across every condition.
        first = next(iter(episodes.values()))['state']
        state = {kind: {obj: {field: tensor(np.concatenate([episodes[d]['state'][kind][obj][field]
                         for _, d in assignments], axis=0)) for field in fields}
                         for obj, fields in objects.items()} for kind, objects in first.items()}
        kp = unwrap(robot.data.joint_stiffness).clone()
        kd = unwrap(robot.data.joint_damping).clone()
        for i, (v, _) in enumerate(assignments):
            kp[i, ids[:7]] *= VARIANTS[v].get('kp', 1)
            kd[i, ids[:7]] *= VARIANTS[v].get('kd', 1)
        robot.write_joint_stiffness_to_sim_index(stiffness=kp)
        robot.write_joint_damping_to_sim_index(damping=kd)
        import omni.usd
        stage = omni.usd.get_context().get_stage()
        effective_attributes = {}
        for prim in stage.Traverse():
            path = str(prim.GetPath())
            if ('env_0' not in path) and path != cfg.sim.physics_prim_path:
                continue
            for attr in prim.GetAttributes():
                name = attr.GetName()
                if name in ['physxArticulation:solverPositionIterationCount', 'physxArticulation:solverVelocityIterationCount',
                            'physxScene:enableExternalForcesEveryIteration', 'physxScene:solverType']:
                    value = attr.Get()
                    effective_attributes[path+'/'+name] = str(value) if not isinstance(value, (bool, int, float)) else value
        (args.output/'effective-physics-attributes.json').write_text(json.dumps(effective_attributes, indent=2))
        assert any(k.endswith('solverPositionIterationCount') and v == args.position_iterations for k,v in effective_attributes.items())
        assert any(k.endswith('solverVelocityIterationCount') and v == args.velocity_iterations for k,v in effective_attributes.items())
        assert any(k.endswith('enableExternalForcesEveryIteration') and v == args.external_forces_every_iteration
                   for k,v in effective_attributes.items())
        materials = None
        if any('friction' in VARIANTS[v] for v, _ in assignments):
            import warp as wp
            raw_materials = cube.root_view.get_material_properties()
            materials = wp.to_torch(raw_materials).clone()
            for i, (v, _) in enumerate(assignments):
                materials[i, :, :2] *= VARIANTS[v].get('friction', 1.)
            material_indices = wp.array(np.arange(n, dtype=np.int32), device=raw_materials.device)
            cube.root_view.set_material_properties(wp.from_torch(materials.contiguous()), material_indices)
            checked = wp.to_torch(cube.root_view.get_material_properties())
            assert torch.allclose(checked, materials)
        ff = tensor([VARIANTS[v].get('gravity_ff', False) for v, _ in assignments], dtype=torch.bool)
        effort = torch.zeros_like(unwrap(robot.data.joint_pos))
        speeds = np.array([VARIANTS[v].get('speed', 1.) for v, _ in assignments])
        thresholds = dict(minimum_lift_m=.03, stable_release_s=.5, ee_gate_m=args.gate_distance,
                          ee_gate_rad=.18, maximum_task_s=args.timeout_s,
                          placement='original full-footprint pad criterion, height +/-8mm, cube speed <=.03m/s, angular speed <=.5rad/s, both fingers >=.3rad')
        provenance = dict(args={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                          assignments=assignments, controller='Feedback tracking of observed source TCP pose path; time advances only inside the common pose-error gate. No fixed joint-target replay.',
                          active_joint_names=active, joint_units=['rad']*9,
                          action_semantics='request/pre/post/applied are absolute joint radians, seven arm joints plus two rotary fingers; source EE commands are separate.',
                          success=thresholds, phases=PHASES, physics_dt=float(env.physics_dt), control_dt=1/30,
                          runtime_stiffness=unwrap(robot.data.joint_stiffness).cpu().tolist(),
                          runtime_damping=unwrap(robot.data.joint_damping).cpu().tolist(),
                          cube_materials=materials.tolist() if materials is not None else None,
                          script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          task_mdp_sha256=hashlib.sha256(Path(mdp.__file__).read_bytes()).hexdigest())
        (args.output/'provenance.json').write_text(json.dumps(provenance, indent=2))
        successes = []
        for repeat in range(args.repeats):
            env.reset_to(state, env_ids=None, seed=11+repeat*11, is_relative=True)
            env.action_manager.reset()
            assert torch.allclose(unwrap(robot.data.joint_stiffness), kp)
            assert torch.allclose(unwrap(robot.data.joint_damping), kd)
            initial_z = unwrap(cube.data.root_pos_w)[:, 2].cpu().numpy().copy()
            progress = np.zeros(n)
            done = np.zeros(n, bool)
            lifted = np.zeros(n, bool)
            stable = np.zeros(n, int)
            final = [None]*n
            arrays = {key: [] for key in ['request', 'pre', 'post', 'applied', 'source_action', 'phase', 'time',
                                          'cube_position', 'cube_velocity', 'ee_error_m', 'reference_index', 'active', 'placed']}
            substep_sums = np.zeros((n, 3))
            substep_counts = np.zeros(n, int)
            total = int(np.ceil(args.timeout_s*30))
            if args.max_frames is not None:
                total = min(total, args.max_frames)
            for step in range(total):
                pre = unwrap(robot.data.joint_pos)[:, ids].clone()
                ee_p, ee_q = pose._compute_frame_pose()
                indices = [min(int(progress[i]), len(episodes[d]['values']['actions'])-1) for i, (_, d) in enumerate(assignments)]
                target_p = tensor(np.stack([episodes[d]['values']['obs/left_tcp_pos'][idx] for idx, (_, d) in zip(indices, assignments)]))
                target_q = tensor(np.stack([episodes[d]['values']['obs/left_tcp_quat'][idx] for idx, (_, d) in zip(indices, assignments)]))
                dp, dq = compute_pose_error(ee_p, ee_q, target_p, target_q, rot_error_type='axis_angle')
                distances = dp.norm(dim=-1).cpu().numpy()
                angles = dq.norm(dim=-1).cpu().numpy()
                command = torch.cat((torch.clamp(dp*args.outer_gain/.02, -1, 1),
                                     torch.clamp(dq*args.outer_gain/.1, -1, 1),
                                     tensor([[episodes[d]['values']['actions'][idx, -1]] for idx, (_, d) in zip(indices, assignments)])), dim=-1)
                command[tensor(done)] = 0
                phase = np.array([0 if idx<episodes[d]['close'] else 1 if idx<episodes[d]['lift'] else
                                  2 if idx<episodes[d]['release'] else 3 for idx, (_, d) in zip(indices, assignments)])
                env.action_manager.process_action(command)
                request = None
                mask = ~done
                for _ in range(cfg.decimation):
                    env.action_manager.apply_action()
                    a = torch.cat((pose._joint_pos_command, fingers.processed_actions), -1)
                    u = torch.cat((pose._joint_pos_target, fingers._applied_targets), -1)
                    q = unwrap(robot.data.joint_pos)[:, ids].clone()
                    if request is None:
                        request = a.clone()
                    if ff.any():
                        effort.zero_()
                        effort[ff] = unwrap(robot.data.gravity_compensation_forces)[ff, -robot.num_joints:]
                        robot.set_joint_effort_target_index(target=effort)
                    env.scene.write_data_to_sim()
                    env.sim.step(render=False)
                    env.scene.update(dt=float(env.physics_dt))
                    for j, delta in enumerate([a-u, u-q, u-unwrap(robot.data.joint_pos)[:, ids]]):
                        substep_sums[mask, j] += delta[:, :7].abs().mean(-1).cpu().numpy()[mask]*180/np.pi
                    substep_counts[mask] += 1
                post = unwrap(robot.data.joint_pos)[:, ids].clone()
                raw_placed = mdp.cube_placed_on_pad(env, robot_cfg=SceneEntityCfg('robot', joint_names=[active[7]])).cpu().numpy()
                z = unwrap(cube.data.root_pos_w)[:, 2].cpu().numpy()
                lifted |= z >= initial_z + .03
                accepted_place = raw_placed & (phase == 3) & (command[:, -1].cpu().numpy() > 0)
                stable, now_success = stable_success(accepted_place, lifted, post[:, 7:].cpu().numpy(), stable, 15)
                fallen = mdp.cube_below_table(env).cpu().numpy()
                for key, value in [('request', request), ('pre', pre), ('post', post), ('applied', u),
                                   ('source_action', command), ('phase', phase), ('time', np.full(n, step/30)),
                                   ('cube_position', unwrap(cube.data.root_pos_w)-env.scene.env_origins),
                                   ('cube_velocity', unwrap(cube.data.root_lin_vel_w)), ('ee_error_m', distances),
                                   ('reference_index', np.asarray(indices)), ('active', mask.copy()), ('placed', raw_placed)]:
                    arrays[key].append(value.detach().cpu().numpy().copy() if isinstance(value, torch.Tensor) else value.copy())
                for i in range(n):
                    if not done[i] and (now_success[i] or fallen[i]):
                        done[i] = True
                        final[i] = 'success' if now_success[i] else 'cube_fallen'
                    if not done[i] and distances[i] <= args.gate_distance and angles[i] <= .18:
                        progress[i] += speeds[i]
                if step % 300 == 0:
                    print('TASK_PROGRESS '+json.dumps(dict(repeat=repeat, step=step, done=int(done.sum()),
                         successful=sum(x=='success' for x in final), reference_range=[float(progress.min()),float(progress.max())],
                         wall_seconds=round(time.monotonic()-started, 1))), flush=True)
                if done.all():
                    break
            stacked = {k: np.asarray(v) for k, v in arrays.items()}
            for i, (variant, demo) in enumerate(assignments):
                keep = stacked['active'][:, i]
                trial = {k: v[keep, i] for k, v in stacked.items() if k!='active'}
                assert all(np.isfinite(x).all() for x in trial.values())
                name = f'{variant}-{demo}-r{repeat}'
                np.savez_compressed(args.output/(name+'.npz'), **trial)
                stats = summarize(trial, 1/30)
                stats.update(variant=variant, demo=demo, repeat=repeat, seed=11+repeat*11,
                             success=final[i]=='success', end_reason=final[i] or 'timeout', lifted=bool(lifted[i]),
                             reference_frames_reached=float(progress[i]), substeps=int(substep_counts[i]),
                             physics_request_applied_mae_deg=float(substep_sums[i, 0]/substep_counts[i]),
                             physics_applied_pre_mae_deg=float(substep_sums[i, 1]/substep_counts[i]),
                             physics_applied_post_mae_deg=float(substep_sums[i, 2]/substep_counts[i]))
                successes.append(stats)
            (args.output/'trials.json').write_text(json.dumps(successes, indent=2))
        (args.output/'complete.json').write_text(json.dumps(dict(trials=len(successes), success=sum(x['success'] for x in successes),
                                                               wall_seconds=time.monotonic()-started), indent=2))
        print('TASK_EXPERIMENT_COMPLETE '+str(args.output), flush=True)
    except BaseException:
        import traceback
        message = traceback.format_exc()
        (args.output/'error.txt').write_text(message)
        print(message, file=sys.__stderr__, flush=True)
        raise
    finally:
        if env is not None:
            env.close()
        app.close()


if __name__ == '__main__':
    main()
