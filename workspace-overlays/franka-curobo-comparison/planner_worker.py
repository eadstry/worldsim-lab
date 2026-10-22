"""Isolated installed cuRobo v1 process; JSON stdin requests, atomic JSON replies.

The carried-object sphere is planning geometry only. It never creates a simulation
constraint or changes the physical cube. The tabletop proxy has a small opening
at the fixed robot mount; the rest of the home stays in the physical simulation.
"""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--obstacle", action="store_true")
parser.add_argument("--probe", action="store_true")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)

import numpy as np
import torch
from curobo.geom.sdf.world import CollisionCheckerType
from curobo.geom.types import Cuboid, WorldConfig
from curobo.types.base import TensorDeviceType
from curobo.types.math import Pose
from curobo.types.state import JointState
from curobo.util_file import get_robot_configs_path, join_path, load_yaml
from curobo.wrap.reacher.motion_gen import MotionGen, MotionGenConfig, MotionGenPlanConfig
from metrics import BLOCK_CENTER, BLOCK_HALF, TARGET_XY


def write(name, value):
    path = args.output / name
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)


def main():
    t0 = time.perf_counter()
    device = TensorDeviceType(device=torch.device("cuda:0"))
    boxes = [
        Cuboid("floor", pose=[0, 0, -.80, 1, 0, 0, 0], dims=[10, 10, .1]),
        Cuboid("table_main", pose=[.6818, -.011, -.025, 1, 0, 0, 0], dims=[1.0636, .8, .05]),
        Cuboid("table_left_front", pose=[.0269, -.2805, -.025, 1, 0, 0, 0], dims=[.2462, .261, .05]),
        Cuboid("table_left_back", pose=[.0269, .2695, -.025, 1, 0, 0, 0], dims=[.2462, .239, .05]),
    ]
    if args.obstacle:
        boxes.append(Cuboid("blocker", pose=BLOCK_CENTER.tolist() + [1, 0, 0, 0], dims=(2*BLOCK_HALF).tolist()))
    world = WorldConfig(cuboid=boxes)
    robot = load_yaml(join_path(get_robot_configs_path(), "franka.yml"))["robot_cfg"]
    cfg = MotionGenConfig.load_from_robot_config(
        robot, world, tensor_args=device, collision_checker_type=CollisionCheckerType.PRIMITIVE,
        num_trajopt_seeds=4, num_graph_seeds=4, num_ik_seeds=32, trajopt_tsteps=32,
        interpolation_dt=.02, collision_activation_distance=.02,
        position_threshold=.002, rotation_threshold=.02, use_cuda_graph=True,
    )
    planner = MotionGen(cfg)
    planner.warmup(enable_graph=True, warmup_js_trajopt=False)
    torch.cuda.synchronize()
    initialization = time.perf_counter() - t0
    write("ready.json", dict(initialization_s=initialization, joint_names=planner.joint_names,
                             obstacles=[b.name for b in boxes], world_scope="local table/floor/blocker proxies"))

    def solve(request):
        torch.cuda.synchronize()
        started = time.perf_counter()
        q = device.to_device([request["joint_pos"]])
        start = JointState.from_position(q, joint_names=planner.joint_names)
        state = planner.compute_kinematics(start)
        fk = state.ee_pos_seq.reshape(-1, 3)[0].detach().cpu().numpy()
        quat_wxyz = state.ee_quat_seq.reshape(-1, 4)[0].detach().cpu().numpy()
        result = dict(fk_position=fk.tolist(), fk_quaternion_wxyz=quat_wxyz.tolist())
        if "hand_pose_xyzw" in request:
            actual = np.asarray(request["hand_pose_xyzw"])
            result["fk_position_error_m"] = float(np.linalg.norm(fk - actual[:3]))
            actual_wxyz = actual[[6, 3, 4, 5]]
            dot = min(1.0, abs(float(np.dot(actual_wxyz, quat_wxyz))))
            result["fk_rotation_error_rad"] = float(2 * np.arccos(dot))
            assert result["fk_position_error_m"] < .003, result
            assert result["fk_rotation_error_rad"] < .03, result
        if "attached_center_hand" in request:
            center = request["attached_center_hand"]
            spheres = device.to_device([center + [.035]] * 4)
            planner.attach_spheres_to_robot(sphere_tensor=spheres)
        goal = Pose.from_list(request["goal_hand_wxyz"], device)
        output = planner.plan_single(start, goal, MotionGenPlanConfig(
            max_attempts=4, timeout=20, enable_graph_attempt=1, enable_finetune_trajopt=True,
        ))
        torch.cuda.synchronize()
        result.update(success=bool(output.success.item()), status=str(output.status),
                      synchronized_request_s=time.perf_counter() - started,
                      reported_solve_s=float(output.solve_time), initialization_s=initialization,
                      torch_allocated_mib=torch.cuda.memory_allocated()/1048576,
                      torch_reserved_mib=torch.cuda.memory_reserved()/1048576)
        if result["success"]:
            plan = output.get_interpolated_plan().get_ordered_joint_state(planner.joint_names)
            trajectory = plan.position.detach().cpu().numpy()
            assert np.isfinite(trajectory).all()
            result.update(trajectory=trajectory.tolist(), interpolation_dt=.02,
                          planned_seconds=(len(trajectory)-1)*.02)
        planner.detach_spheres_from_robot()
        return result

    if args.probe:
        request = dict(joint_pos=[0, -.569, 0, -2.81, 0, 3.037, .741],
                       goal_hand_wxyz=[*TARGET_XY, .3534, 0, 1, 0, 0])
        write("probe.json", solve(request))
        return
    for line in sys.stdin:
        request = json.loads(line)
        if request.get("op") == "close":
            break
        try:
            result = solve(request)
        except Exception as error:
            traceback.print_exc()
            result = dict(success=False, error=repr(error))
        write(f"response-{request['id']:04d}.json", result)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        traceback.print_exc()
        raise
