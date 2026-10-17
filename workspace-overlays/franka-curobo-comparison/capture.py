"""Record one physical Franka IK pick/lift/place trajectory in the home scene.

Uses the current Isaac Lab Franka high-PD configuration and differential-IK tutorial
controller. This is a scripted demonstration, not Mimic augmentation or policy inference.
All manipulator motion after initialization uses joint targets; no cube attachment,
pose writes, collision disabling, or kinematic animation is used during the episode.
"""
import argparse
import hashlib
import json
import os
import sys
import traceback
import time
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--home", type=Path, required=True)
parser.add_argument("--robot-usd", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--method", choices=("ik", "curobo"), required=True)
parser.add_argument("--obstacle", action="store_true")
parser.add_argument("--trial", type=int, choices=(0, 1, 2), required=True)
parser.add_argument("--planner-python", required=True)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
assert args.home.is_file() and args.robot_usd.is_file()
args.output.mkdir(parents=True, exist_ok=False)
process_started = time.perf_counter()
app = AppLauncher(vars(args).copy(), enable_cameras=True).app

import h5py
import imageio_ffmpeg
import numpy as np
import torch
from PIL import Image

import isaaclab.sim as sim_utils
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg
from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg
from isaaclab.managers import SceneEntityCfg
from isaaclab.scene import InteractiveScene, InteractiveSceneCfg
from isaaclab.sensors import CameraCfg, ContactSensorCfg
from isaaclab.utils.configclass import configclass
from isaaclab.utils.math import (
    create_rotation_matrix_from_view, quat_apply, quat_apply_inverse, quat_from_matrix, matrix_from_quat,
    skew_symmetric_matrix, subtract_frame_transforms,
)
from isaaclab_assets.robots.franka import FRANKA_PANDA_HIGH_PD_CFG
from metrics import PICK_POSITIONS, BLOCK_CENTER, BLOCK_HALF, TARGET_XY, signed_aabb_clearance, trajectory_metrics
from planner_client import PlannerClient
from pxr import Usd, UsdPhysics

# PhysX requires one body per filter expression. A Robot/.* filter expands to
# multiple bodies and fails initialization, so enumerate the source rigid bodies.
robot_stage = Usd.Stage.Open(str(args.robot_usd.resolve()))
robot_root = str(robot_stage.GetDefaultPrim().GetPath())
robot_filters = ["{ENV_REGEX_NS}/Robot" + str(prim.GetPath()).removeprefix(robot_root)
                 for prim in robot_stage.Traverse() if prim.HasAPI(UsdPhysics.RigidBodyAPI)]

pick_x, pick_y = PICK_POSITIONS[args.trial]
torch.manual_seed(101 + args.trial)


def camera(prim, eye, target, width=960, height=540, focal=24):
    rotation = quat_from_matrix(create_rotation_matrix_from_view(torch.tensor([eye]), torch.tensor([target])))[0]
    return CameraCfg(
        prim_path=prim, update_period=0, width=width, height=height, data_types=["rgb"],
        spawn=sim_utils.PinholeCameraCfg(focal_length=focal, horizontal_aperture=36,
                                       clipping_range=(0.03, 100)),
        offset=CameraCfg.OffsetCfg(pos=eye, rot=tuple(rotation.tolist()), convention="opengl"),
    )


@configclass
class HomeSceneCfg(InteractiveSceneCfg):
    home = AssetBaseCfg(prim_path="{ENV_REGEX_NS}/Home",
                        spawn=sim_utils.UsdFileCfg(usd_path=str(args.home.resolve())))
    light = AssetBaseCfg(prim_path="/World/Dome", spawn=sim_utils.DomeLightCfg(intensity=1200))
    key = AssetBaseCfg(prim_path="/World/Key", spawn=sim_utils.DiskLightCfg(
        intensity=1000, radius=1.5), init_state=AssetBaseCfg.InitialStateCfg(pos=(0.4, 0.0, 2.0)))
    robot = FRANKA_PANDA_HIGH_PD_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")
    robot.spawn.usd_path = str(args.robot_usd.resolve())
    cube = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Cube",
        spawn=sim_utils.CuboidCfg(
            size=(0.04, 0.04, 0.04), mass_props=sim_utils.MassPropertiesCfg(mass=0.05),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(solver_position_iteration_count=16,
                solver_velocity_iteration_count=4, max_depenetration_velocity=1),
            collision_props=sim_utils.CollisionPropertiesCfg(contact_offset=0.002, rest_offset=0),
            physics_material=sim_utils.RigidBodyMaterialCfg(static_friction=1.0, dynamic_friction=0.8),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.9, 0.12, 0.04)),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=(pick_x, pick_y, 0.027)),
    )
    # A visual target painted onto the original dining tabletop; not a replacement table.
    target = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/Target",
        spawn=sim_utils.CuboidCfg(size=(0.12, 0.12, 0.001),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.08, 0.5, 0.15))),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(*TARGET_XY, 0.001)),
    )
    blocker = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Blocker", spawn=sim_utils.CuboidCfg(
            size=tuple(2*BLOCK_HALF), activate_contact_sensors=True,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True, disable_gravity=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=1),
            collision_props=sim_utils.CollisionPropertiesCfg(contact_offset=.002, rest_offset=0),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(.08, .25, .85))),
        init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(BLOCK_CENTER)))
    blocker_contact = ContactSensorCfg(
        prim_path="{ENV_REGEX_NS}/Blocker", update_period=0,
        filter_prim_paths_expr=robot_filters + ["{ENV_REGEX_NS}/Cube"])
    overview = camera("{ENV_REGEX_NS}/Overview", (1.65, -1.1, 1.55), (0.4, -.05, 0.28), focal=22)
    detail = camera("{ENV_REGEX_NS}/Detail", (1.25, -0.5, 0.85), (0.35, -0.05, 0.15),
                    width=640, height=480, focal=28)
    house = camera("{ENV_REGEX_NS}/House", (0.6, -3.2, 10.5), (0.6, -3.0, -0.75),
                   width=640, height=640, focal=26)


def main():
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=0.005, device=args.device, render_interval=4))
    scene_cfg = HomeSceneCfg(num_envs=1, env_spacing=2.0)
    if not args.obstacle:
        scene_cfg.blocker = None
        scene_cfg.blocker_contact = None
    scene = InteractiveScene(scene_cfg)
    sim.reset()
    scene.reset()
    robot, cube = scene["robot"], scene["cube"]
    # InteractiveScene stores default joint poses but does not apply the state
    # reset used by ManagerBasedEnv. Match the native IK tutorial explicitly.
    initial_q = robot.data.default_joint_pos.torch.clone()
    robot.write_joint_position_to_sim_index(position=initial_q)
    robot.write_joint_velocity_to_sim_index(velocity=robot.data.default_joint_vel.torch.clone())
    robot.reset()
    robot.set_joint_position_target_index(target=initial_q)
    scene.write_data_to_sim()
    sim.step(render=False)
    scene.update(0.005)
    import omni.usd
    from pxr import Usd, UsdGeom
    table_path = "/World/envs/env_0/Home/Home/livingRoom1/livingRoom1_diningtable_1587793_yflib019/lib_1587793/diningTable002/mesh059"
    table = omni.usd.get_context().get_stage().GetPrimAtPath(table_path)
    assert table, "Native dining table missing after spawning"
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeWorldBound(table).ComputeAlignedBox()
    assert abs(bounds.GetMax()[2]) < 1e-4, "Spawner changed the table height"
    assert bounds.GetMin()[0] < 0.5 < bounds.GetMax()[0] and bounds.GetMin()[1] < TARGET_XY[1] < 0.0 < bounds.GetMax()[1]
    entity = SceneEntityCfg("robot", joint_names=["panda_joint.*"], body_names=["panda_hand"])
    entity.resolve(scene)
    fingers, _ = robot.find_joints("panda_finger.*")
    jidx = entity.body_ids[0] - 1 if robot.is_fixed_base else entity.body_ids[0]
    dofs = [j + robot.num_base_dofs for j in entity.joint_ids]
    ik = DifferentialIKController(DifferentialIKControllerCfg(
        command_type="pose", use_relative_mode=False, ik_method="dls"), 1, sim.device)
    tip_offset = torch.tensor([[0, 0, 0.1034]], device=sim.device)
    quat = [1.0, 0.0, 0.0, 0.0]  # XYZW: tool z points down.
    phases = [
        ("approach", 100, (pick_x, pick_y, 0.22), 0.04),
        ("descend", 150, (pick_x, pick_y, 0.024), 0.04),
        ("grasp", 75, (pick_x, pick_y, 0.024), 0.0),
        ("lift", 125, (pick_x, pick_y, 0.25), 0.0),
        ("transfer", 125, (*TARGET_XY, 0.25), 0.0),
        ("lower_prepare", 90, (*TARGET_XY, 0.075), 0.0),
        ("lower", 60, (*TARGET_XY, 0.026), 0.0),
        ("release", 75, (*TARGET_XY, 0.026), 0.04),
        ("retreat", 100, (*TARGET_XY, 0.23), 0.04),
        ("settle", 100, (*TARGET_XY, 0.23), 0.04),
    ]
    snapshots = []
    video = imageio_ffmpeg.write_frames(str(args.output / "overview.mp4"), (960, 540), fps=50,
        codec="libx264", pix_fmt_in="rgb24", macro_block_size=1, output_params=["-crf", "21"])
    video.send(None)
    close_video = imageio_ffmpeg.write_frames(str(args.output / "detail.mp4"), (640, 480), fps=50,
        codec="libx264", pix_fmt_in="rgb24", macro_block_size=1, output_params=["-crf", "21"])
    close_video.send(None)
    records = {k: [] for k in ("actions", "joint_pos", "joint_vel", "cube_state", "tcp_pose", "phase", "blocker_contact_n", "cube_blocker_clearance_m")}
    # Open the dataset early so partial output remains inspectable on a later failure.
    f = h5py.File(args.output / "episodes.hdf5", "x")
    group = f.create_group("data/demo_0")
    group.attrs["joint_names"] = json.dumps(robot.joint_names)
    obs = group.create_group("obs")
    # Keep state/action HDF5 small; both complete RGB streams are retained as MP4.
    peak_z = -float("inf")
    settled_run = 0
    max_settled_run = 0
    lifted = False
    initial_z = None
    frame = 0
    planner = None
    plan_results = []
    planning_failed = False
    control_compute_s = 0.0
    phase_times = {}
    episode_started = time.perf_counter()
    initial_robot = robot.data.joint_pos.torch[0].cpu().numpy().tolist()
    initial_cube = cube.data.root_state_w.torch[0].cpu().numpy().tolist()
    try:
        if args.method == "curobo":
            planner = PlannerClient(args.planner_python, (args.output / "planner").resolve(), args.obstacle)
        for phase_id, (name, steps, target, gripper) in enumerate(phases):
            phase_started = time.perf_counter()
            start_pose = robot.data.body_pose_w.torch[:, entity.body_ids[0]].clone()
            start_tip = start_pose[:, :3] + quat_apply(start_pose[:, 3:], tip_offset)
            target = torch.tensor([target], device=sim.device)
            joint_plan = None
            if name in ("transfer", "lower_prepare") and planner is not None:
                cube_pos = cube.data.root_pose_w.torch[:, :3]
                center_hand = quat_apply_inverse(start_pose[:, 3:], cube_pos - start_pose[:, :3])[0].cpu().tolist()
                goal_hand = target[0].cpu().numpy() - np.array([0, 0, -.1034])
                result = planner.plan(dict(
                    joint_pos=robot.data.joint_pos.torch[0, entity.joint_ids].cpu().tolist(),
                    hand_pose_xyzw=start_pose[0].cpu().tolist(), attached_center_hand=center_hand,
                    goal_hand_wxyz=goal_hand.tolist() + [0, 1, 0, 0]))
                result["phase"] = name
                if "error" in result:
                    raise RuntimeError(f"cuRobo integration error, not a task planning failure: {result}")
                plan_results.append({k:v for k,v in result.items() if k != "trajectory"})
                if not result["success"]:
                    planning_failed = True
                    break
                joint_plan = np.asarray(result["trajectory"], dtype=np.float32)
                steps = max(steps, len(joint_plan) + 30)
            for i in range(steps):
                control_started = time.perf_counter()
                # Smooth each waypoint transition, with time left at the target to settle.
                alpha = min((i + 1) / (steps * 0.75), 1.0)
                alpha = alpha * alpha * (3 - 2 * alpha)
                desired_pos = start_tip * (1 - alpha) + target * alpha
                command = torch.cat((desired_pos, torch.tensor([quat], device=sim.device)), dim=-1)
                hand = robot.data.body_pose_w.torch[:, entity.body_ids[0]]
                root = robot.data.root_pose_w.torch
                offset_w = quat_apply(hand[:, 3:], tip_offset)
                tip = hand[:, :3] + offset_w
                tip_b, quat_b = subtract_frame_transforms(root[:, :3], root[:, 3:], tip, hand[:, 3:])
                jacobian = robot.data.body_link_jacobian_w.torch[:, jidx, :, dofs].clone()
                jacobian[:, :3] -= torch.bmm(skew_symmetric_matrix(offset_w), jacobian[:, 3:])
                # Fixed root is identity; command and Jacobian share the robot base frame.
                ik.set_command(command)
                q = robot.data.joint_pos.torch[:, entity.joint_ids]
                if joint_plan is None:
                    q_target = ik.compute(tip_b, quat_b, jacobian, q)
                else:
                    progress = min(i / max(steps - 31, 1), 1.0) * (len(joint_plan) - 1)
                    lower = int(progress)
                    upper = min(lower + 1, len(joint_plan) - 1)
                    q_target = torch.tensor(joint_plan[lower] * (1 - progress + lower) + joint_plan[upper] * (progress - lower), device=sim.device).reshape(1, -1)
                # Small target increments turn the high-PD controller into a slow
                # velocity command. Permit enough correction to track the path.
                q_target = torch.clamp(q_target, q - 0.2, q + 0.2)
                assert torch.isfinite(q_target).all(), "Nonfinite controller targets"
                robot.set_joint_position_target_index(target=q_target, joint_ids=entity.joint_ids)
                robot.set_joint_position_target_index(
                    target=torch.full((1, len(fingers)), gripper, device=sim.device), joint_ids=fingers)
                control_compute_s += time.perf_counter() - control_started
                contact_peak = 0.0
                for _ in range(4):
                    scene.write_data_to_sim()
                    sim.step(render=False)
                    scene.update(0.005)
                    if args.obstacle:
                        force = scene["blocker_contact"].data.force_matrix_w
                        assert force is not None, "Filtered blocker contact forces unavailable"
                        contact_peak = max(contact_peak, float(torch.linalg.vector_norm(force.torch, dim=-1).max()))
                sim.render()
                state = cube.data.root_state_w.torch[0].cpu().numpy().copy()
                assert np.isfinite(state).all(), "Nonfinite cube state"
                if initial_z is None and frame >= 30:
                    initial_z = float(state[2])
                peak_z = max(peak_z, float(state[2]))
                lifted |= bool(initial_z is not None and float(state[2]) - initial_z > 0.15)
                speed = float(np.linalg.norm(state[7:10]))
                in_target = bool(abs(state[0] - TARGET_XY[0]) < 0.04 and abs(state[1] - TARGET_XY[1]) < 0.04
                                 and abs(state[2] - 0.02) < 0.015)
                good = lifted and in_target and speed < 0.02 and gripper == 0.04 and name in ("retreat", "settle")
                settled_run = settled_run + 1 if good else 0
                max_settled_run = max(max_settled_run, settled_run)
                rgb = scene["overview"].data.output["rgb"][0, ..., :3].cpu().numpy().copy()
                detail = scene["detail"].data.output["rgb"][0, ..., :3].cpu().numpy().copy()
                video.send(rgb)
                close_video.send(detail)
                records["actions"].append(np.r_[q_target[0].cpu().numpy(), gripper, gripper])
                records["joint_pos"].append(robot.data.joint_pos.torch[0].cpu().numpy().copy())
                records["joint_vel"].append(robot.data.joint_vel.torch[0].cpu().numpy().copy())
                records["cube_state"].append(state)
                hand_now = robot.data.body_pose_w.torch[:, entity.body_ids[0]]
                tip_now = hand_now[:, :3] + quat_apply(hand_now[:, 3:], tip_offset)
                records["tcp_pose"].append(torch.cat((tip_now, hand_now[:, 3:]), -1)[0].cpu().numpy().copy())
                records["phase"].append(phase_id)
                records["blocker_contact_n"].append(contact_peak)
                rotation = matrix_from_quat(cube.data.root_pose_w.torch[:, 3:])[0].cpu().numpy()
                half_extent = np.abs(rotation) @ np.array([.02, .02, .02])
                records["cube_blocker_clearance_m"].append(signed_aabb_clearance(state[:3], half_extent) if args.obstacle else 0.0)
                if i == steps - 1:
                    Image.fromarray(rgb).save(args.output / f"{phase_id:02d}-{name}.png")
                    if name == "lift":
                        house = scene["house"].data.output["rgb"][0, ..., :3].cpu().numpy().copy()
                        Image.fromarray(house).save(args.output / "house-with-robot.png")
                    snapshots.append(f"{phase_id:02d}-{name}.png")
                frame += 1
            print(json.dumps(dict(phase=name, frames=frame, cube=state[:3].tolist(),
                tcp=records["tcp_pose"][-1][:3].tolist(),
                speed=speed, lifted=lifted, max_stable_steps=max_settled_run)), flush=True)
            phase_times[name] = time.perf_counter() - phase_started
        success = lifted and settled_run >= 50
        actions = np.asarray(records["actions"])
        group.create_dataset("actions", data=actions)
        for key, value in records.items():
            if key == "actions":
                continue
            obs.create_dataset(key, data=np.asarray(value))
        group.attrs["success"] = bool(success)
        group.attrs["num_samples"] = frame
        f["data"].attrs["total"] = frame
        group.attrs["fps"] = 50
        group.attrs["action_description"] = "seven arm joint position targets (rad), then two finger joint targets (m); obs is post-step"
        group.attrs["generator"] = f"{args.method}: common IK contact stages, compared transfer and pre-place stages"
        group.attrs["phase_names"] = json.dumps([p[0] for p in phases])
        summary = dict(success=bool(success), frames=frame, fps=50, seconds=frame / 50,
            robot="Franka Panda", native_surface="scene000430 original dining table",
            initial_cube_z=initial_z, peak_cube_z=peak_z, final_cube_state=state.tolist(),
            final_speed_m_s=speed, final_stable_steps=settled_run,
            success_criterion="lift > .15 m then place within .04 m XY and .015 m Z of target, released, speed < .02 m/s for final >=50 steps",
            method=args.method, obstacle=args.obstacle, trial=args.trial,
            planning_failed=planning_failed, completed=True,
            collision_free_success=bool(success and max(records["blocker_contact_n"], default=0) < 1.0),
            peak_blocker_contact_n=max(records["blocker_contact_n"], default=0),
            blocker_contact_steps=sum(force >= 1.0 for force in records["blocker_contact_n"]),
            minimum_cube_aabb_blocker_clearance_m=min(records["cube_blocker_clearance_m"], default=0) if args.obstacle else None,
            initial_robot_joint_pos=initial_robot, initial_cube_state=initial_cube,
            control_compute_s=control_compute_s, phase_wall_s=phase_times,
            planning=plan_results, planner_initialization_s=planner.ready["initialization_s"] if planner else 0,
            planner_startup_wall_s=planner.ready["worker_startup_wall_s"] if planner else 0,
            episode_wall_s=time.perf_counter()-episode_started,
            measured_process_s=time.perf_counter()-process_started,
            trajectory=trajectory_metrics(records["joint_pos"], actions, records["tcp_pose"]),
            generator="common IK contact stages; transfer and pre-place: local IK versus cuRobo joint plan",
            snapshots=snapshots, home=str(args.home.resolve()), robot_usd=str(args.robot_usd.resolve()),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            cameras={name: dict(eye=list(scene[name].cfg.offset.pos), rotation_xyzw=list(scene[name].cfg.offset.rot),
                width=scene[name].cfg.width, height=scene[name].cfg.height,
                focal_length=scene[name].cfg.spawn.focal_length,
                horizontal_aperture=scene[name].cfg.spawn.horizontal_aperture) for name in ("overview", "detail")})
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        if planner is not None:
            planner.close()
        f.close()
        video.close()
        close_video.close()
    # A completed physical/planning failure is an experimental result, not a startup failure.


if __name__ == "__main__":
    try:
        with torch.inference_mode():
            main()
    except BaseException:
        # Kit shutdown may otherwise replace an exception's exit status with zero.
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    app.close()
