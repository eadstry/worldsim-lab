# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Joint-command variant of the existing blue-cube scene for KER teleoperation."""

from isaaclab.envs import mdp
from isaaclab.utils.configclass import configclass

from openarm_autodata.shared.configs.robot_v2_cfg import (
    OPENARM_V2_LEFT_ARM_JOINT_NAMES,
    OPENARM_V2_LEFT_FINGER_JOINT_NAMES,
    OPENARM_V2_RIGHT_ARM_JOINT_NAMES,
    OPENARM_V2_RIGHT_FINGER_JOINT_NAMES,
)

from .env_cfg import OpenArmBimanualPickPlaceEnvCfg
from .left_env_cfg import OpenArmLeftPickPlaceEnvCfg


@configclass
class KerActionsCfg:
    """Seven absolute arm angles followed by two synchronized finger angles [rad]."""

    right_arm = mdp.JointPositionActionCfg(
        asset_name="robot",
        joint_names=list(OPENARM_V2_RIGHT_ARM_JOINT_NAMES),
        use_default_offset=False,
        preserve_order=True,
    )
    right_fingers = mdp.JointPositionActionCfg(
        asset_name="robot",
        joint_names=list(OPENARM_V2_RIGHT_FINGER_JOINT_NAMES),
        use_default_offset=False,
        preserve_order=True,
    )


@configclass
class KerLeftActionsCfg:
    """Seven absolute left-arm angles followed by two left-finger angles [rad]."""

    left_arm = mdp.JointPositionActionCfg(
        asset_name="robot",
        joint_names=list(OPENARM_V2_LEFT_ARM_JOINT_NAMES),
        use_default_offset=False,
        preserve_order=True,
    )
    left_fingers = mdp.JointPositionActionCfg(
        asset_name="robot",
        joint_names=list(OPENARM_V2_LEFT_FINGER_JOINT_NAMES),
        use_default_offset=False,
        preserve_order=True,
    )


@configclass
class OpenArmKerPickPlaceEnvCfg(OpenArmBimanualPickPlaceEnvCfg):
    """Reuse the blue cube, robot, sensors and success condition with joint control."""

    actions: KerActionsCfg = KerActionsCfg()


@configclass
class OpenArmKerLeftPickPlaceEnvCfg(OpenArmLeftPickPlaceEnvCfg):
    """Left-arm joint-control variant of the blue-cube scene."""

    actions: KerLeftActionsCfg = KerLeftActionsCfg()

    def __post_init__(self):
        super().__post_init__()
        # Absolute KER following starts with the physical leader and simulation at zero.
        self.scene.robot.init_state.joint_pos["openarm_left_joint4"] = 0.0
