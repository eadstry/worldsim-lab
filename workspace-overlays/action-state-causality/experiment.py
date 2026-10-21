"""Queued OpenArm replay and fixed joint-command interventions; never edit production configuration."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np


VARIANTS = {
    "baseline": {}, "repeat": {},
    "kp_half": {"kp": 0.5}, "kp_double": {"kp": 2.0},
    "kd_half": {"kd": 0.5}, "kd_double": {"kd": 2.0},
    "speed_half": {"speed": 0.5}, "speed_double": {"speed": 2.0},
    "rate_0p1": {"rate": 0.1}, "rate_unbinding": {"rate": 100.0},
    "control_15hz": {"decimation": 8}, "no_cube": {"no_cube": True},
    "gravity_feedforward": {"gravity_ff": True},
    "effort_double": {"effort": 2.0}, "velocity_double": {"velocity": 2.0},
}


def unwrap(x):
    return getattr(x, "torch", x)


def load_source(path, demo):
    with h5py.File(path, "r") as f:
        meta = json.loads(f["data"].attrs["env_args"])
        d = f[f"data/{demo}"]
        result = {k: d[k][:] for k in ("actions", "joint_actions", "joint_applied_targets", "obs/joint_pos_absolute")}
        state = {}
        def visit(k, value):
            if isinstance(value, h5py.Dataset):
                node = state
                parts = k.split("/")
                for name in parts[:-1]:
                    node = node.setdefault(name, {})
                node[parts[-1]] = value[:]
        d["initial_state"].visititems(visit)
    return result, state, meta


def summarize(arrays):
    a, q, u, post = (arrays[k] for k in ("request", "pre", "applied", "post"))
    result = {}
    for key, delta in (("request_pre", a-q), ("request_applied", a-u),
                       ("applied_pre", u-q), ("request_post", a-post), ("applied_post", u-post)):
        degrees = np.abs(delta[:, :7]) * 180 / np.pi
        result[key] = {"mae_deg": float(degrees.mean()), "p95_deg": float(np.quantile(degrees, .95)),
                       "per_joint_mae_deg": degrees.mean(0).tolist()}
    for j in (7, 8):
        closed = np.isclose(a[:, j], 0) & np.isclose(u[:, j], 0)
        result[f"finger_{j-6}_settled_closed"] = {
            "n": int(closed.sum()), "median_rad": float(np.median(q[closed, j])) if closed.any() else None}
    result["frames"] = len(a)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--autodata-root", type=Path, required=True)
    p.add_argument("--compat-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mode", choices=("source", "fixed"), default="fixed")
    p.add_argument("--demo", default="demo_0")
    p.add_argument("--variants", nargs="+", choices=tuple(VARIANTS), default=list(VARIANTS))
    p.add_argument("--no-collisions", action="store_true")
    p.add_argument("--max-frames", type=int)
    args = p.parse_args()
    if args.max_frames is not None and args.max_frames <= 0:
        p.error("--max-frames must be positive")
    if args.mode == "fixed" and "baseline" not in args.variants:
        p.error("fixed interventions require baseline in --variants")
    args.output.mkdir(parents=True, exist_ok=False)
    source, initial, meta = load_source(args.source, args.demo)
    if args.max_frames:
        source = {k: v[:args.max_frames] for k, v in source.items()}
    sys.path[:0] = [str(args.runtime.resolve()), str(args.autodata_root.resolve()), str(args.compat_root.resolve())]
    from isaaclab.app import AppLauncher
    launcher = AppLauncher(headless=True, enable_cameras=False)
    app, env = launcher.app, None
    start = time.monotonic()
    try:
        import gymnasium as gym
        import torch
        from compat import install_task_compat
        install_task_compat()
        import openarm_autodata.tasks.pick_place  # noqa: F401
        from isaaclab.managers import ObservationTermCfg
        from collision_audit import audit, disable_before_physics
        from isaaclab_tasks.utils.parse_cfg import parse_env_cfg

        variant_names = ["baseline"] if args.mode == "source" else args.variants
        n = len(variant_names)
        task = "Isaac-PickPlace-Cube-OpenArm-Bimanual-Left-IK-Rel-v0"
        cfg = parse_env_cfg(task, device="cuda:0", num_envs=n)
        cfg.terminations = None
        cfg.recorders = None
        cfg.scene.env_spacing = 4.0
        for camera in ("left_hand_camera", "right_hand_camera", "third_person_camera", "ee_frame"):
            setattr(cfg.scene, camera, None)
        for name, term in list(vars(cfg.observations.policy).items()):
            if isinstance(term, ObservationTermCfg) and name not in ("joint_pos", "joint_vel"):
                setattr(cfg.observations.policy, name, None)
        cfg.observations.subtask_terms = None
        if args.no_collisions:
            disable_before_physics(cfg)
        env = gym.make(task, cfg=cfg).unwrapped
        collisions = audit(env.sim.stage, expect_disabled=args.no_collisions)
        robot = env.scene["robot"]
        names = list(robot.joint_names)
        active_names = meta["semantic_metadata"]["joint_control"]["names"]
        ids = [names.index(name) for name in active_names]
        state = {kind: {name: {key: torch.as_tensor(value, device=env.device).expand(n, *value.shape[1:]).clone()
                               for key, value in fields.items()} for name, fields in objects.items()}
                 for kind, objects in initial.items()}
        for i, name in enumerate(variant_names):
            if VARIANTS[name].get("no_cube"):
                state["rigid_object"]["cube"]["root_pose"][i, :3] = torch.tensor([5., 5., 0.], device=env.device)
        env.reset_to(state, env_ids=None, seed=1, is_relative=True)
        # Match source controller reset to the restored pose, not the event's default pose.
        env.action_manager.reset()
        kp = unwrap(robot.data.joint_stiffness).clone()
        kd = unwrap(robot.data.joint_damping).clone()
        effort = unwrap(robot.data.joint_effort_limits).clone()
        velocity_limits = unwrap(robot.data.joint_vel_limits).clone()
        for i, name in enumerate(variant_names):
            kp[i, ids[:7]] *= VARIANTS[name].get("kp", 1.)
            kd[i, ids[:7]] *= VARIANTS[name].get("kd", 1.)
            effort[i, ids[:7]] *= VARIANTS[name].get("effort", 1.)
            velocity_limits[i, ids[:7]] *= VARIANTS[name].get("velocity", 1.)
        robot.write_joint_stiffness_to_sim_index(stiffness=kp)
        robot.write_joint_damping_to_sim_index(damping=kd)
        robot.write_joint_effort_limit_to_sim_index(limits=effort)
        robot.write_joint_velocity_limit_to_sim_index(limits=velocity_limits)
        physics_dt = float(env.physics_dt)
        control_dt = float(meta["semantic_metadata"]["control_dt"])
        provenance = {"args": {k: str(v) if isinstance(v, Path) else v for k,v in vars(args).items()},
                      "experiment_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "collision_helper_sha256": hashlib.sha256(Path(__file__).with_name("collision_audit.py").read_bytes()).hexdigest(),
                      "collision_audit": collisions,
                      "source_metadata": meta, "joint_names": names, "active_ids": ids,
                      "runtime_stiffness": unwrap(robot.data.joint_stiffness).cpu().tolist(),
                      "runtime_damping": unwrap(robot.data.joint_damping).cpu().tolist(),
                      "runtime_effort_limits": unwrap(robot.data.joint_effort_limits).cpu().tolist(),
                      "runtime_velocity_limits": unwrap(robot.data.joint_vel_limits).cpu().tolist(),
                      "variant_parameters": {name: VARIANTS[name] for name in variant_names},
                      "robot_collisions_disabled": args.no_collisions,
                      "physics_dt": physics_dt, "rendering": False,
                      "torque_evidence": "implicit actuator computed_torque/applied_torque are estimates, not measured drive torque",
                      "scope": "one saved trajectory; fixed mode bypasses IK and replays requested absolute joint targets"}
        (args.output / "provenance.json").write_text(json.dumps(provenance, indent=2))
        (args.output / "experiment-source.py").write_text(Path(__file__).read_text())
        (args.output / "collision-audit-source.py").write_text(Path(__file__).with_name("collision_audit.py").read_text())
        records = {name: {k: [] for k in ("request", "pre", "applied", "post", "pre_velocity", "time")}
                   for name in variant_names}
        substeps = []
        if args.mode == "source":
            pose = env.action_manager.get_term("left_arm_action")
            fingers = env.action_manager.get_term("left_gripper_action")
            for t, action in enumerate(source["actions"]):
                rec = records["baseline"]
                rec["pre"].append(unwrap(robot.data.joint_pos)[0, ids].cpu().numpy().copy())
                rec["pre_velocity"].append(unwrap(robot.data.joint_vel)[0, ids].cpu().numpy().copy())
                env.step(torch.as_tensor(action, device=env.device).unsqueeze(0))
                rec["post"].append(unwrap(robot.data.joint_pos)[0, ids].cpu().numpy().copy())
                rec["request"].append(torch.cat((pose._joint_pos_command, fingers.processed_actions), -1)[0].cpu().numpy().copy())
                rec["applied"].append(torch.cat((pose._joint_pos_target, fingers._applied_targets), -1)[0].cpu().numpy().copy())
                rec["time"].append(t * control_dt)
                if t % 200 == 0:
                    print(f"SOURCE_REPLAY {t}/{len(source['actions'])}", flush=True)
        else:
            command = torch.as_tensor(source["joint_actions"], device=env.device)
            applied = unwrap(robot.data.joint_pos)[:, ids].clone()
            request = applied.clone()
            speed = np.array([VARIANTS[name].get("speed", 1.) for name in variant_names])
            decimation = np.array([VARIANTS[name].get("decimation", 4) for name in variant_names])
            ends = np.ceil(len(command) * control_dt / speed / physics_dt).astype(int)
            limits = torch.tensor([[VARIANTS[name].get("rate", 2.)]*7 + [1., 1.] for name in variant_names], device=env.device)
            ff = torch.zeros(n, dtype=torch.bool, device=env.device)
            for i, name in enumerate(variant_names):
                ff[i] = VARIANTS[name].get("gravity_ff", False)
            ff_effort = torch.zeros_like(unwrap(robot.data.joint_pos))
            pending = {}
            for tick in range(int(ends.max())):
                now = tick * physics_dt
                for i, name in enumerate(variant_names):
                    if tick >= ends[i] or tick % decimation[i]:
                        continue
                    # Zero-order hold of the original trajectory as a function of physical time.
                    index = min(int(np.floor((now * speed[i] + 1e-8) / control_dt)), len(command)-1)
                    request[i] = command[index]
                    rec = records[name]
                    rec["request"].append(request[i].cpu().numpy().copy())
                    rec["pre"].append(unwrap(robot.data.joint_pos)[i, ids].cpu().numpy().copy())
                    rec["pre_velocity"].append(unwrap(robot.data.joint_vel)[i, ids].cpu().numpy().copy())
                    rec["time"].append(now)
                    pending[i] = min(tick + int(decimation[i])-1, int(ends[i])-1)
                applied += torch.clamp(request-applied, min=-limits*physics_dt, max=limits*physics_dt)
                robot.set_joint_position_target_index(target=applied, joint_ids=ids)
                if ff.any():
                    g = unwrap(robot.data.gravity_compensation_forces)
                    ff_effort.zero_()
                    ff_effort[ff] = g[ff, -robot.num_joints:]
                    robot.set_joint_effort_target_index(target=ff_effort)
                pre = unwrap(robot.data.joint_pos)[:, ids].clone()
                env.scene.write_data_to_sim()
                env.sim.step(render=False)
                env.scene.update(dt=physics_dt)
                post = unwrap(robot.data.joint_pos)[:, ids].clone()
                # Save all physics substeps; end-of-control targets alone can hide ramping.
                substeps.append(torch.stack((request, applied, pre, post, unwrap(robot.data.joint_vel)[:, ids]), 1).cpu().numpy())
                for i, end_tick in list(pending.items()):
                    if tick == end_tick:
                        records[variant_names[i]]["post"].append(post[i].cpu().numpy().copy())
                        records[variant_names[i]]["applied"].append(applied[i].cpu().numpy().copy())
                        del pending[i]
                if tick % 1200 == 0:
                    print(f"FIXED_REPLAY {tick}/{int(ends.max())}", flush=True)
        summary = {}
        for name, values in records.items():
            arrays = {k: np.asarray(v) for k, v in values.items()}
            if not all(np.isfinite(a).all() for a in arrays.values()):
                raise RuntimeError(f"Non-finite state in {name}")
            np.savez_compressed(args.output / f"{name}.npz", **arrays)
            summary[name] = summarize(arrays)
        if substeps:
            np.savez_compressed(args.output / "physics-substeps.npz", values=np.asarray(substeps),
                                fields=np.array(["request", "applied", "pre", "post", "post_velocity"]),
                                variants=np.array(variant_names), physics_dt=physics_dt)
        if args.mode == "source":
            q = np.asarray(records["baseline"]["pre"])
            a = np.asarray(records["baseline"]["request"])
            summary["historical_reproduction"] = {
                "pre_state_mae_rad": float(np.abs(q-source["obs/joint_pos_absolute"]).mean()),
                "request_mae_rad": float(np.abs(a-source["joint_actions"]).mean()),
                "source_arm_mae_deg": float(np.abs(source["joint_actions"][:,:7]-source["obs/joint_pos_absolute"][:,:7]).mean()*180/np.pi)}
        summary["wall_seconds"] = time.monotonic()-start
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
        print("EXPERIMENT_PASSED " + str(args.output), flush=True)
    finally:
        if env is not None:
            env.close()
        app.close()


if __name__ == "__main__":
    main()
