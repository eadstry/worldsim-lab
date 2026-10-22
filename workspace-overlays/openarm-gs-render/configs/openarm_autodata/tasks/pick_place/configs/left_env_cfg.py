# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Left-arm pick-place variant using the same scene and task rules as the right arm."""

from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.configclass import configclass

from openarm_autodata.shared.configs.robot_v2_cfg import (
    OPENARM_V2_LEFT_ARM_JOINT_NAMES,
    OPENARM_V2_LEFT_EE_BODY_NAME,
    OPENARM_V2_LEFT_FINGER_JOINT_NAMES,
    OPENARM_V2_LEFT_GRIPPER_OPEN_POSITION,
)

from .env_cfg import ActionsCfg, ObservationsCfg, OpenArmBimanualPickPlaceEnvCfg
from .scene_layout import load_scene_layout


@configclass
class LeftActionsCfg:
    """Six relative TCP coordinates followed by one binary left-gripper action."""

    left_arm_action = ActionsCfg().right_arm_action.replace(
        joint_names=list(OPENARM_V2_LEFT_ARM_JOINT_NAMES),
        body_name=OPENARM_V2_LEFT_EE_BODY_NAME,
    )
    left_gripper_action = ActionsCfg().right_gripper_action.replace(
        joint_names=list(OPENARM_V2_LEFT_FINGER_JOINT_NAMES),
        open_command_expr={name: OPENARM_V2_LEFT_GRIPPER_OPEN_POSITION for name in OPENARM_V2_LEFT_FINGER_JOINT_NAMES},
        close_command_expr={name: 0.0 for name in OPENARM_V2_LEFT_FINGER_JOINT_NAMES},
    )


@configclass
class LeftObservationsCfg(ObservationsCfg):
    """Expose the controlled TCP and gripper under explicitly left-arm keys."""

    @configclass
    class PolicyCfg(ObservationsCfg.PolicyCfg):
        right_tcp_pos = None
        right_tcp_quat = None
        right_tcp_pos_env = None
        right_tcp_quat_env = None
        right_gripper_pos = None
        left_tcp_pos = ObservationsCfg.PolicyCfg().right_tcp_pos.copy()
        left_tcp_quat = ObservationsCfg.PolicyCfg().right_tcp_quat.copy()
        left_tcp_pos_env = ObservationsCfg.PolicyCfg().right_tcp_pos_env.copy()
        left_tcp_quat_env = ObservationsCfg.PolicyCfg().right_tcp_quat_env.copy()
        left_gripper_pos = ObservationsCfg.PolicyCfg().right_gripper_pos.replace(
            params={"robot_cfg": SceneEntityCfg("robot", joint_names=[OPENARM_V2_LEFT_FINGER_JOINT_NAMES[0]])}
        )

    policy: PolicyCfg = PolicyCfg()


@configclass
class OpenArmLeftPickPlaceEnvCfg(OpenArmBimanualPickPlaceEnvCfg):
    """Bind the left-arm workspace and park the right arm at zero."""

    actions: LeftActionsCfg = LeftActionsCfg()
    observations: LeftObservationsCfg = LeftObservationsCfg()

    def __post_init__(self):
        super().__post_init__()
        target = self.scene.ee_frame.target_frames[0]
        target.prim_path = target.prim_path.replace("openarm_right", "openarm_left")
        target.name = "left_tcp"
        self.scene.cube.init_state.pos = load_scene_layout(self.scene_name)["cube_spawn_left"]
        # Raise the open hand clear of the 1.060 m desk for keyboard recording.
        # The KER subclass separately restores its active arm to the leader's zero pose.
        self.scene.robot.init_state.joint_pos["openarm_left_joint4"] = load_scene_layout(self.scene_name).get(
            "left_elbow_angle", 1.5
        )
        # Keep each existing regex unique; zero both passive arm and passive fingers.
        for pattern in self.scene.robot.init_state.joint_pos:
            if "openarm_right" in pattern:
                self.scene.robot.init_state.joint_pos[pattern] = 0.0
        for term in (self.observations.subtask_terms.grasp, self.terminations.success):
            term.params["robot_cfg"] = SceneEntityCfg("robot", joint_names=[OPENARM_V2_LEFT_FINGER_JOINT_NAMES[0]])
