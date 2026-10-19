# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Experimental single-environment cuRobo v2 backend for the OpenArm SkillGen contract."""
from __future__ import annotations

from copy import deepcopy
import functools
import os
from types import SimpleNamespace

import torch
from curobo.kinematics import KinematicsCfg
from curobo.motion_planner import MotionPlanner, MotionPlannerCfg
from curobo.sphere_fit import SphereFitType
from curobo.types import DeviceCfg, GoalToolPose, JointState, Pose
# These two utilities have no public exports in the pinned v2 revision.
from curobo._src.types.robot import RobotCfg
from curobo._src.util.usd_scene_parser import UsdSceneParser


from trajectory import resample_path
from model import convert_robot


class CuroboPlanner:
    """Preserve OpenArm contact phases, joint mapping, attachments and EE waypoint output."""

    def __init__(self, datastream, config, env_id: int = 0, **kwargs) -> None:
        self.datastream, self.config, self.env_id = datastream, config, env_id
        self.step_size = config.motion_step_size
        self.plan_config = SimpleNamespace(max_attempts=config.max_planning_attempts)
        self.device_cfg = DeviceCfg(device=f"cuda:{config.cuda_device or 0}")
        self._current_plan = None
        self._grip = False
        self._index = 0
        self._base = datastream.get_robot_root_pose(env_ids=[env_id])[0]
        self._inverse_base = torch.linalg.inv(self._base)
        self._parser = UsdSceneParser()
        self._parser.load_stage(datastream.get_usd_stage())
        self._scene = self._parser.get_obstacles_from_stage(
            only_paths=[datastream.get_env_prim_path(env_id)],
            reference_prim_path=config.robot_prim_path or datastream.get_robot_prim_path(env_id),
            ignore_substring=config.world_ignore_substrings,
        ).get_collision_check_world()
        robot = convert_robot(config.get_robot_config())
        kin = robot["kinematics"]
        kin["extra_collision_spheres"] = deepcopy(config.extra_collision_spheres)
        kin["grasp_contact_link_names"] = list(config.hand_link_names)
        self._robot_data = robot
        # Precompute both lock states, then copy parameters in-place so CUDA graph addresses stay stable.
        self._grip_models = {}
        for closed, positions in [(False, config.gripper_open_positions), (True, config.gripper_closed_positions)]:
            data = deepcopy(robot)
            data["kinematics"]["lock_joints"].update(positions)
            self._grip_models[closed] = KinematicsCfg.from_robot_yaml_file(data)
        self._grip_params = {closed: model.kinematics_config.clone()
                             for closed, model in self._grip_models.items()}
        cfg = MotionPlannerCfg.create(
            robot=RobotCfg(self._grip_models[False], device_cfg=self.device_cfg),
            scene_model=self._scene,
            collision_cache={"mesh": config.collision_cache_size["mesh"],
                             "cuboid": config.collision_cache_size["obb"]},
            num_ik_seeds=32,
            num_trajopt_seeds=config.num_trajopt_seeds,
            interpolation_dt=config.interpolation_dt,
            interpolation_buffer_size=1000,
            position_tolerance=config.position_threshold,
            orientation_tolerance=config.rotation_threshold,
            optimizer_collision_activation_distance=config.collision_activation_distance,
            random_seed=1531,  # Match v1 MotionGen's default IK seed.
            use_cuda_graph=True,
            device_cfg=self.device_cfg,
        )
        if not config.enable_graph:
            cfg.graph_planner_config = None
        self.motion_gen = MotionPlanner(cfg)
        # plan_pose otherwise hardcodes an extra refinement pass in the pinned v2 revision.
        # Match the existing OpenArm profile's disabled finetuning without editing cuRobo.
        if not config.enable_finetune_trajopt:
            solve_pose = self.motion_gen.trajopt_solver.solve_pose

            @functools.wraps(solve_pose)
            def solve_without_refinement(*args, **kwargs):
                kwargs['finetune_attempts'] = 0
                return solve_pose(*args, **kwargs)

            self.motion_gen.trajopt_solver.solve_pose = solve_without_refinement
        if 'MVP_METRICS_FILE' in os.environ:
            from metrics import emit
            transition = cfg.trajopt_solver_config.metrics_rollout_config.transition_model_cfg
            emit('backend_configuration', control_space=transition.control_space.name,
                 random_seed=1531,
                 n_knots=transition.n_knots, rollout_horizon=transition.horizon,
                 interpolation_steps=transition.interpolation_steps,
                 num_ik_seeds=cfg.ik_solver_config.num_seeds,
                 num_trajopt_seeds=cfg.trajopt_solver_config.num_seeds,
                 finetune_enabled=config.enable_finetune_trajopt,
                 use_cuda_graph=cfg.trajopt_solver_config.core_cfg.use_cuda_graph,
                 graph_enabled=self.motion_gen.graph_planner is not None,
                 active_joint_names=self.motion_gen.joint_names,
                 scene_obstacles=[dict(name=o.name, kind=type(o).__name__) for o in self._scene.objects])
        self._closed = False
        print("MVP v2 planner: active joints", self.motion_gen.joint_names, flush=True)
        print("MVP v2 scene:", [(o.name, type(o).__name__) for o in self._scene.objects], flush=True)

    def _state(self, position: torch.Tensor | None = None) -> JointState:
        if position is None:
            all_names = self.datastream.get_robot_joint_names()
            position = self.datastream.get_robot_joint_positions(env_ids=[self.env_id])
            indices = [all_names.index(name) for name in self.motion_gen.joint_names]
            position = position[:, indices]
        return JointState.from_position(position.reshape(-1, len(self.motion_gen.joint_names)).contiguous(),
                                        joint_names=self.motion_gen.joint_names)

    def _ee_pose(self, state: JointState) -> Pose:
        return self.motion_gen.compute_kinematics(state).tool_poses.get_link_pose(self.config.ee_link_name)

    def reset_plan(self) -> None:
        self._current_plan, self._index = None, 0

    def _update_world(self) -> None:
        self._base = self.datastream.get_robot_root_pose(env_ids=[self.env_id])[0]
        self._inverse_base = torch.linalg.inv(self._base)
        objects = self.datastream.get_object_poses(env_ids=[self.env_id])
        for name, values in objects.items():
            if name in self.config.static_objects:
                continue
            pose = Pose.from_matrix(self._inverse_base @ values[0])
            matches = [o for o in self._scene.objects if name.lower() in o.name.lower()]
            assert matches, f"No collision geometry for dynamic object {name}"
            for obstacle in matches:
                obstacle.pose = pose.tolist()
                self.motion_gen.scene_collision_checker.update_obstacle_pose(
                    obstacle.name, pose, env_idx=0)

    def _set_gripper(self, closed: bool) -> None:
        params = self._grip_params[closed]
        for kin in [self.motion_gen.ik_solver.kinematics, self.motion_gen.trajopt_solver.kinematics]:
            kin.update_kinematics_config(params)
        self._grip = closed

    def _plan_to_contact_pose(self, start_state: JointState, goal_pose: Pose, contact: bool = True) -> bool:
        links = list(self.config.hand_link_names)
        if contact:
            links.append(self.config.attached_object_link_name)
        params = self.motion_gen.kinematics.config.kinematics_config
        saved = {name: params.get_link_spheres(name).clone() for name in links} if contact else {}
        try:
            if contact:
                self.motion_gen.disable_link_collision(links)
            goals = GoalToolPose.from_poses({self.config.ee_link_name: goal_pose},
                                            ordered_tool_frames=self.motion_gen.tool_frames)
            result = self.motion_gen.plan_pose(goals, start_state, max_attempts=self.config.max_planning_attempts)
            if result is None or not bool(result.success.all().item()):
                return False
            # The spline control points are not executable samples. Use the dense trajectory.
            trajectory = result.get_interpolated_plan()
            assert trajectory is not None
            # Returned states can include the locked gripper. Select by name before flattening.
            assert trajectory.joint_names is not None, 'Trajectory has no joint identities'
            trajectory = trajectory.reorder(self.motion_gen.joint_names)
            assert trajectory.position.shape[-1] == len(self.motion_gen.joint_names)
            self._current_plan = trajectory.position.reshape(-1, len(self.motion_gen.joint_names)).clone()
            assert torch.isfinite(self._current_plan).all()
            return True
        finally:
            for name, spheres in saved.items():
                params.update_link_spheres(name, spheres)

    @torch.inference_mode(False)
    @torch.enable_grad()
    def update_world_and_plan_motion(self, target_pose: torch.Tensor,
                                     expected_attached_object: str | None = None, env_id: int = 0,
                                     step_size: float | None = None, enable_retiming: bool = False) -> bool:
        assert env_id == self.env_id
        self.reset_plan()
        self._update_world()
        self._set_gripper(expected_attached_object is not None)
        state = self._state()
        attached = False
        try:
            if expected_attached_object:
                names = self.datastream.get_robot_joint_names()
                joint = self.datastream.get_robot_joint_positions(env_ids=[env_id])[0,
                         names.index(self.config.gripper_joint_names[0])].item()
                grasped = joint > self.config.grasp_gripper_open_val if self.config.gripper_closes_on_increasing_position else joint < self.config.grasp_gripper_open_val
                assert grasped, "Expected carried object but gripper is not closed"
                objects = [o.name for o in self._scene.objects if expected_attached_object.lower() in o.name.lower()]
                assert objects, f"No obstacle to attach: {expected_attached_object}"
                # Scene fitting produces base-frame centers. Identity offset makes update apply EE^-1.
                identity = Pose.from_matrix(torch.eye(4, device=state.position.device))
                self.motion_gen.attachment_manager.attach_from_scene(
                    state, objects, link_name=self.config.attached_object_link_name,
                    num_spheres=self.config.extra_collision_spheres[self.config.attached_object_link_name],
                    surface_radius=self.config.surface_sphere_radius,
                    sphere_fit_type=SphereFitType.SURFACE, world_objects_pose_offset=identity)
                attached = True
            goal = Pose.from_matrix(self._inverse_base @ target_pose)
            targets, contacts = [], []
            if self.config.retreat_distance and self.config.retreat_distance > 0:
                offset = Pose.from_list([self.config.retreat_distance * axis for axis in self.config.contact_offset_axis]
                                        + [1.0, 0.0, 0.0, 0.0], device_cfg=self.device_cfg)
                targets.append(self._ee_pose(state).multiply(offset))
                contacts.append(True)
            if self.config.approach_distance and self.config.approach_distance > 0:
                offset = Pose.from_list([self.config.approach_distance * axis for axis in self.config.contact_offset_axis]
                                        + [1.0, 0.0, 0.0, 0.0], device_cfg=self.device_cfg)
                targets.append(goal.multiply(offset))
                contacts.append(False)
                targets.append(goal)
                contacts.append(True)
            else:
                targets.append(goal)
                contacts.append(False)
            segments = []
            for target, contact in zip(targets, contacts):
                if not self._plan_to_contact_pose(start_state=state, goal_pose=target, contact=contact):
                    self.reset_plan()
                    return False
                segments.append(self._current_plan)
                state = self._state(self._current_plan[-1])
            path = torch.cat(segments)
            self._current_plan = resample_path(path, step_size) if enable_retiming and step_size else path
            return True
        finally:
            if attached:
                self.motion_gen.attachment_manager.detach(self.config.attached_object_link_name)

    def get_planned_poses(self) -> list[torch.Tensor]:
        if self._current_plan is None:
            return []
        with torch.no_grad():
            matrices = self._ee_pose(self._state(self._current_plan)).get_matrix().reshape(-1, 4, 4)
            result = list(self._base @ matrices)
            if result and self.config.n_repeat:
                result.extend([result[-1]] * self.config.n_repeat)
            return result

    def has_next_waypoint(self) -> bool:
        return self._current_plan is not None and self._index < len(self._current_plan)

    def get_next_waypoint_ee_pose(self) -> Pose:
        assert self.has_next_waypoint()
        pose = self._ee_pose(self._state(self._current_plan[self._index]))
        self._index += 1
        return Pose.from_matrix(self._base @ pose.get_matrix().reshape(4, 4))

    def close(self) -> None:
        if not self._closed:
            self.motion_gen.destroy()
            self._closed = True
