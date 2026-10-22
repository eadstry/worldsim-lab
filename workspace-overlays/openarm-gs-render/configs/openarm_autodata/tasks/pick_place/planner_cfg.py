# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""cuRobo obstacle policy and motion settings for the pick-place task."""

from dataclasses import dataclass

from autodata_interfaces.motion_planners.curobo.curobo_planner_cfg import CuroboPlannerCfg
from openarm_autodata.shared.planner_cfg import ROBOT_CONFIG, OpenArmRightPlannerCfg

from .configs.scene_layout import load_scene_layout


def make_openarm_right_planner_cfg(scene_name: str = "gs_table") -> CuroboPlannerCfg:
    """Build a cuRobo planner for the right-arm pick-and-place environment.

    Args:
        scene_name: Scene layout that supplies collision settings.
    """
    layout = load_scene_layout(scene_name)
    return OpenArmRightPlannerCfg(
        robot_config_file=str(ROBOT_CONFIG),
        robot_name="openarm_right",
        ee_link_name="openarm_right_grasp_frame",
        gripper_joint_names=["openarm_right_finger_joint1"],
        gripper_open_positions={"openarm_right_finger_joint1": -0.7},
        gripper_closed_positions={"openarm_right_finger_joint1": 0.0},
        grasp_gripper_open_val=-0.3,
        gripper_closes_on_increasing_position=True,
        hand_link_names=[
            "openarm_right_ee_base_link",
            "openarm_right_ee_link1",
            "openarm_right_ee_link2",
        ],
        static_objects=layout["static_objects"],
        world_ignore_substrings=layout["world_ignore_substrings"],
        collision_spheres_file=None,
        extra_collision_spheres={"attached_object": 16},
        # OpenArm TCP +Z points away from the table.
        contact_offset_axis=(0.0, 0.0, 1.0),
        # Annotated skills begin above the object; adding another approach can exceed reach.
        approach_distance=0.0,
        retreat_distance=0.05,
        num_trajopt_seeds=2,
        num_graph_seeds=4,
        enable_graph=False,
        warmup=False,
        trajopt_tsteps=20,
        max_planning_attempts=2,
        enable_finetune_trajopt=False,
        motion_step_size=0.005,
        n_repeat=10,
        motion_noise_scale=0.0,
    )


def _swap_arm_names(value):
    """Swap model control references; collision geometry stays in its authored link frames."""
    if isinstance(value, str):
        return value.replace("left", "__SIDE__").replace("right", "left").replace("__SIDE__", "right")
    if isinstance(value, list):
        return [_swap_arm_names(item) for item in value]
    if isinstance(value, dict):
        return {_swap_arm_names(key): _swap_arm_names(item) for key, item in value.items()}
    return value


@dataclass
class PickPlaceLeftPlannerCfg(OpenArmRightPlannerCfg):
    """Activate the left chain in the shared model with the passive right arm at zero."""

    arm_home: tuple[float, ...] = (0.0, 0.0, 0.0, 1.5, 0.0, 0.0, 0.0)

    def get_robot_config(self) -> dict:
        config = super().get_robot_config()
        kin = config["kinematics"]
        for key in ("ee_link", "self_collision_ignore", "extra_links", "cspace"):
            kin[key] = _swap_arm_names(kin[key])
        kin["lock_joints"] = {f"openarm_right_joint{i}": 0.0 for i in range(1, 8)}
        kin["lock_joints"].update(openarm_right_finger_joint1=0.0, openarm_left_finger_joint1=0.7)
        kin["cspace"]["retract_config"] = [*self.arm_home, 0.7]
        return config


def make_openarm_left_planner_cfg(scene_name: str = "gs_table") -> CuroboPlannerCfg:
    """Use the same pick-place planning policy with explicit left-arm model bindings.

    Args:
        scene_name: Scene layout that supplies collision settings.
    """
    from copy import deepcopy
    from dataclasses import fields

    right = make_openarm_right_planner_cfg(scene_name)
    cfg = PickPlaceLeftPlannerCfg(**{field.name: deepcopy(getattr(right, field.name)) for field in fields(right)})
    cfg.arm_home = (0.0, 0.0, 0.0, load_scene_layout(scene_name).get("left_elbow_angle", 1.5), 0.0, 0.0, 0.0)
    cfg.robot_name = "openarm_left"
    cfg.ee_link_name = "openarm_left_grasp_frame"
    cfg.gripper_joint_names = ["openarm_left_finger_joint1"]
    cfg.gripper_open_positions = {"openarm_left_finger_joint1": 0.7}
    cfg.gripper_closed_positions = {"openarm_left_finger_joint1": 0.0}
    cfg.grasp_gripper_open_val = 0.3
    cfg.gripper_closes_on_increasing_position = False
    cfg.hand_link_names = ["openarm_left_ee_base_link", "openarm_left_ee_link1", "openarm_left_ee_link2"]
    return cfg
